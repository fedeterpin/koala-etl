import sys 
import os
import logging
import requests
import pyodbc
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dateutil import parser
from dotenv import load_dotenv
from urllib.parse import quote
import time
import random

# ——— [1] Configuración y Logger ———

# Ubicaciones de archivos y carga de .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "config" / ".env")

# se usa para espaciar llamadas
_LAST_BOTMAKER_CALL_TS = 0.0 

# Variable para activar logs de depuración
DEBUGGER = os.getenv("DEBUGGER", "False").lower() in ("1", "true", "yes")
# Controlar si mostramos el body de errores HTTP
LOG_HTTP_BODY = os.getenv("LOG_HTTP_BODY", "False").lower() in ("1", "true", "yes")

# Configuramos el logger con consola + archivo
logger = logging.getLogger("KoalaETL")
logger.setLevel(logging.DEBUG if DEBUGGER else logging.INFO)

# 1) Formato común para todos los handlers
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    "%Y-%m-%d %H:%M:%S"
)

# 2) StreamHandler (consola)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.DEBUG if DEBUGGER else logging.INFO)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# 3) FileHandler (archivo)
log_dir = BASE_DIR / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

file_path = log_dir / "koala_etl.log"
# Por defecto, FileHandler hace append. Para sobreescribir usa mode="w".
file_handler = logging.FileHandler(file_path, encoding="utf-8")
file_handler.setLevel(logging.DEBUG if DEBUGGER else logging.INFO)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# ——— Parámetros de Botmaker (API) ———
BOTMAKER_CLIENT_ID     = os.getenv("BOTMAKER_CLIENT_ID")
BOTMAKER_SECRET_ID     = os.getenv("BOTMAKER_SECRET_ID")
BOTMAKER_TOKEN         = os.getenv("BOTMAKER_TOKEN")
BOTMAKER_REFRESH_TOKEN = os.getenv("BOTMAKER_REFRESH_TOKEN")

# --- Rate limit / retries (opcionales por .env) ---
BOTMAKER_MIN_INTERVAL = float(os.getenv("BOTMAKER_MIN_INTERVAL", "1.20"))  # subí a 1.20s
HTTP_MAX_RETRIES      = int(os.getenv("HTTP_MAX_RETRIES", "6"))
HTTP_BACKOFF_BASE     = float(os.getenv("HTTP_BACKOFF_BASE", "1.7")) # backoff exponencial
HTTP_JITTER_MAX_MS    = int(os.getenv("HTTP_JITTER_MAX_MS", "120"))  # ← pequeño jitter

# Tenant y ventana deslizante
TENANT_ID      = os.getenv("TENANT_ID")
ETL_INITIAL_TS = os.getenv("ETL_INITIAL_TS", "2025-01-01T00:00:00Z")
try:
    WINDOW_DAYS = int(os.getenv("ETL_WINDOW_DAYS", "0"))
except ValueError:
    WINDOW_DAYS = 0

logger.debug("Valor de ETL_INITIAL_TS cargado: %s", ETL_INITIAL_TS)

# Parámetros de conexión a SQL Server
DB_HOST   = os.getenv("DB_HOST")
DB_PORT   = os.getenv("DB_PORT")
DB_NAME   = os.getenv("DB_NAME")
DB_USER   = os.getenv("DB_USER")
DB_PASS   = os.getenv("DB_PASS")
DB_DRIVER = os.getenv("DB_DRIVER", "SQL Server")

CONN_STR = (
    f"Driver={{{DB_DRIVER}}};"
    f"Server={DB_HOST},{DB_PORT};"
    f"Database={DB_NAME};"
    f"UID={DB_USER};"
    f"PWD={DB_PASS};"
)

# ——— Endpoints Botmaker ———

# Usamos la versión v2.0 para endpoints
BOTMAKER_BASE_URL = "https://api.botmaker.com/v2.0"
URL_MESSAGES      = f"{BOTMAKER_BASE_URL}/messages"
URL_AGENT_PERF    = f"{BOTMAKER_BASE_URL}/dashboards/agent-performance"
URL_AGENT_METRICS = f"{BOTMAKER_BASE_URL}/dashboards/agent-metrics"
URL_CHAT          = f"{BOTMAKER_BASE_URL}/chats/{{}}"

# Endpoint de refresco de credenciales (v1.0)
URL_REFRESH = "https://go.botmaker.com/api/v1.0/auth/credentials"

# ——— Headers iniciales para Botmaker ———
# La API v2.0 de Botmaker requiere "access-token" en vez de "Authorization: Bearer"
HEADERS = {
    "Accept": "application/json",
    "access-token": BOTMAKER_TOKEN
}

# ——————————————————————————————————————————————————————————————
# UTILS: FECHAS Y VENTANAS
# ——————————————————————————————————————————————————————————————

def parse_ts(ts_str: str) -> datetime | None:
    """Parsea cadena ISO8601 a datetime UTC. Retorna None si ts_str es None."""
    if not ts_str:
        return None
    try:
        dt = parser.isoparse(ts_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def iso_z(dt: datetime) -> str:
    """Formatea datetime UTC a 'YYYY-MM-DDTHH:MM:SSZ'."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def iso_z_ms(dt: datetime) -> str:
    """Formatea datetime UTC a 'YYYY-MM-DDTHH:MM:SS.fffZ'."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def round_down_hour(dt: datetime) -> datetime:
    """Redondea hacia abajo al inicio de la hora (minutos y segundos a 0)."""
    return dt.replace(minute=0, second=0, microsecond=0)

def _placeholder_path(tenant_id: str, message_id: str, kind: str) -> str:
    # Mantiene el patrón de carpetas, pero deja un marcador sintético
    return f"files\\{tenant_id}\\{message_id}\\{kind}\\(not-downloaded)"

def get_window(last_ts: datetime | None) -> tuple[datetime, datetime]:
    """
    - Si last_ts existe (corridas posteriores): from_dt = last_ts.
      to_dt = min(from_dt + WINDOW_DAYS, ahora) si WINDOW_DAYS>0, 
             o else ahora (si WINDOW_DAYS<=0).
    - Si last_ts es None (primera corrida o etl_control vacío):
      from_dt = ETL_INITIAL_TS parseado.
      to_dt   = min(from_dt + WINDOW_DAYS, ahora) si WINDOW_DAYS>0,
               o else ahora.
    """
    now = datetime.now(timezone.utc)

    if last_ts:
        # Corridas posteriores
        from_dt = last_ts
        if WINDOW_DAYS > 0:
            candidate_to = from_dt + timedelta(days=WINDOW_DAYS)
            to_dt = candidate_to if candidate_to < now else now
        else:
            to_dt = now

    else:
        # Primera corrida
        parsed = parse_ts(ETL_INITIAL_TS)
        if parsed:
            from_dt = parsed
        else:
            # Si ETL_INITIAL_TS inválido, caemos a now-WINDOW_DAYS o simply now
            if WINDOW_DAYS > 0:
                from_dt = now - timedelta(days=WINDOW_DAYS)
            else:
                from_dt = now
        if WINDOW_DAYS > 0:
            candidate_to = from_dt + timedelta(days=WINDOW_DAYS)
            to_dt = candidate_to if candidate_to < now else now
        else:
            to_dt = now

    return from_dt, to_dt

# def get_window(last_ts: datetime | None) -> tuple[datetime, datetime]:
#     """
#     Devuelve la tupla (from_dt, to_dt) para la extracción:
#       - Si last_ts es None (primera corrida o etl_control vacío), arranca desde ETL_INITIAL_TS sin recorte.
#       - Si last_ts NO es None, arranca desde last_ts y, si WINDOW_DAYS > 0, recorta a máximo WINDOW_DAYS.
#     """
#     to_dt = datetime.now(timezone.utc)

#     if last_ts:
#         # Corridas posteriores: uso last_ts
#         from_dt = last_ts

#         # Si ETL_WINDOW_DAYS > 0, recorto la ventana a WINDOW_DAYS
#         if WINDOW_DAYS > 0:
#             delta = to_dt - from_dt
#             if delta.days > WINDOW_DAYS:
#                 from_dt = to_dt - timedelta(days=WINDOW_DAYS)
#     else:
#         # Primera corrida o etl_control vacío: uso ETL_INITIAL_TS sin recorte
#         parsed = parse_ts(ETL_INITIAL_TS)
#         if parsed:
#             from_dt = parsed
#         else:
#             # Si ETL_INITIAL_TS no es válido, caigo en WINDOW_DAYS atrás (si existe) o en “ahora”
#             if WINDOW_DAYS > 0:
#                 from_dt = to_dt - timedelta(days=WINDOW_DAYS)
#             else:
#                 from_dt = to_dt

#     from_dt = datetime(2025,1,1,0,0, tzinfo=timezone.utc)
#     to_dt = datetime(2025,1,31,0,0, tzinfo=timezone.utc)

#     return from_dt, to_dt

# ——————————————————————————————————————————————————————————————
# CONEXIÓN Y CONTROL DE ETL
# ——————————————————————————————————————————————————————————————

def get_connection() -> pyodbc.Connection:
    """Retorna una conexión a la base de datos SQL Server."""
    return pyodbc.connect(CONN_STR)

def ensure_etl_control_table(cur: pyodbc.Cursor) -> None:
    """
    Crea tabla etl_control si no existe:
      endpoint VARCHAR(50) PRIMARY KEY,
      last_ts  DATETIME2
    """
    cur.execute("""
        IF OBJECT_ID('dbo.etl_control','U') IS NULL
        BEGIN
            CREATE TABLE dbo.etl_control(
                endpoint VARCHAR(50) PRIMARY KEY,
                last_ts  DATETIME2
            );
        END
    """)
    cur.commit()

def get_last_ts(cur: pyodbc.Cursor, endpoint: str) -> datetime | None:
    """Obtiene last_ts para un endpoint dado. Retorna None si no existe o es NULL."""
    cur.execute("SELECT last_ts FROM dbo.etl_control WHERE endpoint = ?", endpoint)
    row = cur.fetchone()
    if not row or not row.last_ts:
        return None
    if isinstance(row.last_ts, datetime):
        return row.last_ts.replace(tzinfo=timezone.utc)
    return parse_ts(str(row.last_ts))

def set_last_ts(cur: pyodbc.Cursor, endpoint: str, ts: datetime) -> None:
    """Inserta o actualiza last_ts para un endpoint dado."""
    existing = get_last_ts(cur, endpoint)
    if existing is None:
        cur.execute(
            "INSERT INTO dbo.etl_control(endpoint, last_ts) VALUES(?, ?)",
            endpoint, ts
        )
    else:
        cur.execute(
            "UPDATE dbo.etl_control SET last_ts = ? WHERE endpoint = ?",
            ts, endpoint
        )
    cur.commit()

# ——————————————————————————————————————————————————————————————
# AUTENTICACIÓN Y PETICIONES A API BOTMAKER
# ——————————————————————————————————————————————————————————————

def refresh_api_credentials() -> None:
    """
    Refresca token de Botmaker usando refresh token.
    Este endpoint (v1.0) devuelve 200 con JSON, o 204 si no hay cambio de credenciales.
    """
    global BOTMAKER_TOKEN, BOTMAKER_REFRESH_TOKEN, HEADERS

    # Preparar encabezados según especificación v1.0
    hdrs = {
        "Accept":       "application/json",
        "clientId":     BOTMAKER_CLIENT_ID,
        "secretId":     BOTMAKER_SECRET_ID,
        "refreshToken": BOTMAKER_REFRESH_TOKEN,
    }

    resp = requests.post(URL_REFRESH, headers=hdrs, timeout=30)

    # Si devuelve 204 → asumimos que no cambió nada
    if resp.status_code == 204:
        logger.info("Refresh API v1.0 respondió 204 – no hay nuevo token.")
        return

    # Si devuelve 200 con JSON
    if resp.status_code == 200:
        try:
            data = resp.json()
        except ValueError:
            logger.error("Refresh API v1.0 devolvió 200 pero sin JSON. Texto: %s", resp.text)
            resp.raise_for_status()

        # Según doc v1.0, los campos vienen en camelCase: accessToken, refreshToken
        new_token = data.get("accessToken") or data.get("access_token")
        new_refresh = data.get("refreshToken") or data.get("refresh_token")

        if not new_token or not new_refresh:
            logger.error("Refresh v1.0 no devolvió campos válidos: %s", data)
            resp.raise_for_status()

        BOTMAKER_TOKEN         = new_token
        BOTMAKER_REFRESH_TOKEN = new_refresh

        # Actualizo headers para próximas llamadas
        HEADERS = {"access-token": BOTMAKER_TOKEN, "Accept": "application/json"}

        logger.info("Token de Botmaker actualizado via v1.0. accessToken nuevo.")
        return

    # Cualquier otro status → error
    logger.error("Error refrescando credenciales [%s]: %s", resp.status_code, resp.text)
    resp.raise_for_status()

# def api_request(method: str, url: str, **kwargs) -> requests.Response:
#     """Realiza petición HTTP a Botmaker, refrescando token si expira (401)."""
#     r = requests.request(method, url, headers=HEADERS, timeout=30, **kwargs)
#     if r.status_code == 401:
#         logger.warning("401 recibido, refrescando token...")
#         refresh_api_credentials()
#         r = requests.request(method, url, headers=HEADERS, timeout=30, **kwargs)
#     if r.status_code >= 400:
#         logger.error("Error en petición %s %s: %s", method, url, r.status_code)
#         logger.error("Body: %s", r.text[:200])
#         r.raise_for_status()
#     return r

# Versión con throttle + reintentos 429/5xx + Retry-After
# Versión con throttle + reintentos 429/5xx + Retry-After
def api_request(method: str, url: str, **kwargs) -> requests.Response:
    """
    Throttle global 1.2 req/seg + backoff en 429/5xx + reintento tras 401 (refresh).
    Solo imprime el body de errores si LOG_HTTP_BODY=true.
    """
    global HEADERS, _LAST_BOTMAKER_CALL_TS

    def _sleep_with_jitter(base: float):
        jitter = random.randint(0, HTTP_JITTER_MAX_MS) / 1000.0
        time.sleep(base + jitter)

    def _throttle():
        now = time.time()
        elapsed = now - _LAST_BOTMAKER_CALL_TS
        if elapsed < BOTMAKER_MIN_INTERVAL:
            _sleep_with_jitter(BOTMAKER_MIN_INTERVAL - elapsed)

    for attempt in range(1, HTTP_MAX_RETRIES + 1):
        _throttle()
        r = requests.request(method, url, headers=HEADERS, timeout=30, **kwargs)

        if r.status_code == 401:
            logger.warning("401 recibido, refrescando token...")
            refresh_api_credentials()
            _throttle()  # evita 2 llamadas en <1s (refresh cuenta para el rate)
            r = requests.request(method, url, headers=HEADERS, timeout=30, **kwargs)

        if r.status_code == 429:
            retry_after_hdr = r.headers.get("Retry-After")
            try:
                wait = float(retry_after_hdr) if retry_after_hdr else max(BOTMAKER_MIN_INTERVAL, HTTP_BACKOFF_BASE ** attempt)
            except Exception:
                wait = max(BOTMAKER_MIN_INTERVAL, HTTP_BACKOFF_BASE ** attempt)
            logger.warning("429 Too Many Requests. Esperando %.2fs (intento %d/%d)…", wait, attempt, HTTP_MAX_RETRIES)
            _sleep_with_jitter(wait)
            continue

        if 500 <= r.status_code < 600:
            wait = max(BOTMAKER_MIN_INTERVAL, HTTP_BACKOFF_BASE ** attempt)
            logger.warning("HTTP %d en %s. Reintento en %.2fs (intento %d/%d)…", r.status_code, url, wait, attempt, HTTP_MAX_RETRIES)
            _sleep_with_jitter(wait)
            continue

        # éxito o error 4xx distinto a 429:
        _LAST_BOTMAKER_CALL_TS = time.time()

        if r.status_code >= 400:
            if r.status_code == 400:
                logger.error("HTTP 400 en %s – probablemente parámetros inválidos (p.ej., ventana > 1 mes).", url)
            else:
                logger.error("Error en petición %s %s: %s", method, url, r.status_code)

            if LOG_HTTP_BODY:
                body = (r.text or "")[:500]
                logger.error("Body: %s", body)
            r.raise_for_status()
        return r

    logger.error("Agotados reintentos para %s %s", method, url)
    r.raise_for_status()

def fetch_all(url: str, params: dict[str, str] | None = None) -> list[dict]:
    """
    Obtiene todos los elementos de un endpoint que pagine con 'nextPage'.
    Si la respuesta viene vacía (status 204 o body vacío) retorna lista vacía.
    """
    items: list[dict] = []
    p = params.copy() if params else {}
    next_url = url

    while next_url:
        resp = api_request("GET", next_url, params=p)

        # Si status 204 o body vacío → no hay JSON que parsear
        if resp.status_code == 204 or not resp.text.strip():
            return items

        try:
            j = resp.json()
        except ValueError:
            logger.warning("fetch_all: respuesta sin JSON en %s → se detiene", next_url)
            return items

        data = j.get("data") or j.get("items")  # depende del endpoint
        if not data:
            return items

        items.extend(data)
        next_page = j.get("nextPage")
        if not next_page:
            break
        
        # Esto para no paginar más rápido de 1 req/seg
        time.sleep(BOTMAKER_MIN_INTERVAL)
        
        p = {}          # nextPage ya trae los parámetros necesarios
        next_url = next_page

    return items

# ——————————————————————————————————————————————————————————————
# ETL: TENANTS, AGENTS, QUEUES, AGENT_PERFORMANCE + REL
# ——————————————————————————————————————————————————————————————

def etl_tenant_agent_queue(cur: pyodbc.Cursor) -> None:
    """
    Inserta tenant estático (TENANT_ID) si no existe.
    """
    logger.info("▶ ETL tenants, agents y queues (solo tenant estático)")
    cur.execute(
        "IF NOT EXISTS(SELECT 1 FROM dbo.tenants WHERE tenant_id = ?) "
        "INSERT INTO dbo.tenants(tenant_id, tenant_name) VALUES(?, ?)",
        TENANT_ID, TENANT_ID, TENANT_ID
    )
    cur.commit()
    logger.debug("Tenant %s asegurado.", TENANT_ID)

def etl_agent_performance(cur: pyodbc.Cursor) -> None:
    """
    ETL para agent_performance y tablas relacionadas:
      - agents
      - queues
      - agent_performance_queues
      - agent_performance
    Controla duplicados basados en (tenant_id, agentEmail, checkin, checkout).
    """
    logger.info("▶ ETL dbo.agent_performance")
    last = get_last_ts(cur, "agent-performance")
    from_dt, to_dt = get_window(last)
    logger.debug("Ventana agent_performance: %s → %s", from_dt, to_dt)

    params = {
        "from": iso_z(from_dt),
        "to":   iso_z(to_dt)
    }
    data = fetch_all(URL_AGENT_PERF, params)
    logger.info("→ %d registros obtenidos de agent-performance", len(data))

    # Asegura tenant
    cur.execute(
        "IF NOT EXISTS(SELECT 1 FROM dbo.tenants WHERE tenant_id = ?) "
        "INSERT INTO dbo.tenants(tenant_id, tenant_name) VALUES(?, ?)",
        TENANT_ID, TENANT_ID, TENANT_ID
    )
    cur.commit()

    count = 0
    for a in data:
        agent_email = a.get("agentEmail")
        agent_name  = a.get("agentName")
        role        = a.get("role")

        # Inserta agente si no existe (PK: tenant_id, agentEmail)
        cur.execute(
            "IF NOT EXISTS(SELECT 1 FROM dbo.agents WHERE tenant_id = ? AND agentEmail = ?) "
            "INSERT INTO dbo.agents(tenant_id, agentEmail, agentName, role) VALUES(?, ?, ?, ?)",
            TENANT_ID, agent_email,
            TENANT_ID, agent_email, agent_name, role
        )

        # Procesa colas y relación M–N
        for queue in a.get("queue", []):
            # Inserta cola si no existe (PK: tenant_id, queue)
            cur.execute(
                "IF NOT EXISTS(SELECT 1 FROM dbo.queues WHERE tenant_id = ? AND queue = ?) "
                "INSERT INTO dbo.queues(tenant_id, queue) VALUES(?, ?)",
                TENANT_ID, queue,
                TENANT_ID, queue
            )
            # Inserta relación agent_performance_queues (PK: tenant_id, agentEmail, queue)
            cur.execute(
                "IF NOT EXISTS(SELECT 1 FROM dbo.agent_performance_queues "
                "WHERE tenant_id = ? AND agentEmail = ? AND queue = ?) "
                "INSERT INTO dbo.agent_performance_queues(tenant_id, agentEmail, queue) VALUES(?, ?, ?)",
                TENANT_ID, agent_email, queue,
                TENANT_ID, agent_email, queue
            )

        # Inserta registro en agent_performance (evita duplicados)
        checkin_ts  = parse_ts(a.get("checkin"))
        checkout_ts = parse_ts(a.get("checkout"))
        cur.execute(
            """
            INSERT INTO dbo.agent_performance(tenant_id, agentEmail, state, checkin, checkout)
            SELECT ?, ?, ?, ?, ?
            WHERE NOT EXISTS(
                SELECT 1 FROM dbo.agent_performance
                WHERE tenant_id = ? AND agentEmail = ? AND checkin = ? AND checkout = ?
            )
            """,
            TENANT_ID, agent_email, a.get("state"), checkin_ts, checkout_ts,
            TENANT_ID, agent_email, checkin_ts, checkout_ts
        )

        count += 1

    # Actualiza last_ts con to_dt
    if data:
        set_last_ts(cur, "agent-performance", to_dt)
        logger.info("✔ agent_performance: %d filas procesadas, last_ts actualizado a %s", count, to_dt)
    else:
        logger.info("— No hay nuevos registros en agent_performance.")
        cur.commit()


# ——————————————————————————————————————————————————————————————
# ETL: AGENT_METRICS
# ——————————————————————————————————————————————————————————————

def etl_agent_metrics(cur: pyodbc.Cursor) -> None:
    """
    ETL para agent_metrics y tablas relacionadas:
      - queues
      - chats
      - agent_metrics (MERGE basado en PK: tenant_id, sessionId)
    """
    logger.info("▶ ETL dbo.agent_metrics")
    last = get_last_ts(cur, "agent-metrics")
    from_dt, to_dt = get_window(last)
    logger.debug("Ventana agent_metrics: %s → %s", from_dt, to_dt)

    all_items: list[dict] = []
    for status in ("open", "closed"):
        params = {
            "from": iso_z_ms(from_dt),
            "to":   iso_z_ms(to_dt),
            "session-status": status
        }
        items = fetch_all(URL_AGENT_METRICS, params)
        all_items.extend(items)
        time.sleep(BOTMAKER_MIN_INTERVAL) 
    logger.info("→ %d registros obtenidos de agent-metrics", len(all_items))

    # Asegura tenant
    cur.execute(
        "IF NOT EXISTS(SELECT 1 FROM dbo.tenants WHERE tenant_id = ?) "
        "INSERT INTO dbo.tenants(tenant_id, tenant_name) VALUES(?, ?)",
        TENANT_ID, TENANT_ID, TENANT_ID
    )
    cur.commit()

    count = 0
    for s in all_items:
        session_id = s.get("sessionId")
        queue      = s.get("queue")
        chat_id    = s.get("chatId")

        # Inserta queue si existe
        if queue:
            cur.execute(
                "IF NOT EXISTS(SELECT 1 FROM dbo.queues WHERE tenant_id = ? AND queue = ?) "
                "INSERT INTO dbo.queues(tenant_id, queue) VALUES(?, ?)",
                TENANT_ID, queue,
                TENANT_ID, queue
            )

        # Inserta chat si existe
        if chat_id:
            cur.execute(
                "IF NOT EXISTS(SELECT 1 FROM dbo.chats WHERE tenant_id = ? AND chatId = ?) "
                "INSERT INTO dbo.chats(tenant_id, chatId) VALUES(?, ?)",
                TENANT_ID, chat_id,
                TENANT_ID, chat_id
            )

        # MERGE en agent_metrics (PK: tenant_id, sessionId)
        cur.execute(
            """
            MERGE dbo.agent_metrics AS target
            USING (
                SELECT
                  ? AS tenant_id,
                  ? AS sessionId,
                  ? AS chatId,
                  ? AS sessionCreationTime,
                  ? AS avgAttendingTime,
                  ? AS avgResponseTime,
                  ? AS queue,
                  ? AS agentName,
                  ? AS agentId,
                  ? AS typification,
                  ? AS closedTime,
                  ? AS openSessions,
                  ? AS closedSessions,
                  ? AS onHold,
                  ? AS opResponseTime,
                  ? AS operatorResponses,
                  ? AS sessionTransferIn,
                  ? AS sessionTransferOut,
                  ? AS sessionTransferOutNoMessages,
                  ? AS closedWithNoMessages,
                  ? AS timeoutNoMessages,
                  ? AS agentTimeout,
                  ? AS userTimeout,
                  ? AS fromQueueAsignToOpAssigned,
                  ? AS fromSessionStartToOpFirstResponse,
                  ? AS fromQueueAsignToOpFirstResponse,
                  ? AS fromOpAssignedToOpFirstResponse,
                  ? AS fromQueueAsignToSessionClosed,
                  ? AS fromOpAssignationToSessionClosed,
                  ? AS sessionTimeout,
                  ? AS conversationLink
            ) AS src
            ON  target.tenant_id = src.tenant_id
            AND target.sessionId = src.sessionId
            WHEN MATCHED THEN
              UPDATE SET
                chatId                     = src.chatId,
                sessionCreationTime        = src.sessionCreationTime,
                avgAttendingTime           = src.avgAttendingTime,
                avgResponseTime            = src.avgResponseTime,
                queue                      = src.queue,
                agentName                  = src.agentName,
                agentId                    = src.agentId,
                typification               = src.typification,
                closedTime                 = src.closedTime,
                openSessions               = src.openSessions,
                closedSessions             = src.closedSessions,
                onHold                     = src.onHold,
                opResponseTime             = src.opResponseTime,
                operatorResponses          = src.operatorResponses,
                sessionTransferIn          = src.sessionTransferIn,
                sessionTransferOut         = src.sessionTransferOut,
                sessionTransferOutNoMessages = src.sessionTransferOutNoMessages,
                closedWithNoMessages       = src.closedWithNoMessages,
                timeoutNoMessages          = src.timeoutNoMessages,
                agentTimeout               = src.agentTimeout,
                userTimeout                = src.userTimeout,
                fromQueueAsignToOpAssigned = src.fromQueueAsignToOpAssigned,
                fromSessionStartToOpFirstResponse = src.fromSessionStartToOpFirstResponse,
                fromQueueAsignToOpFirstResponse   = src.fromQueueAsignToOpFirstResponse,
                fromOpAssignedToOpFirstResponse   = src.fromOpAssignedToOpFirstResponse,
                fromQueueAsignToSessionClosed      = src.fromQueueAsignToSessionClosed,
                fromOpAssignationToSessionClosed   = src.fromOpAssignationToSessionClosed,
                sessionTimeout            = src.sessionTimeout,
                conversationLink          = src.conversationLink
            WHEN NOT MATCHED THEN
              INSERT (
                tenant_id, sessionId, chatId, sessionCreationTime,
                avgAttendingTime, avgResponseTime, queue, agentName,
                agentId, typification, closedTime, openSessions,
                closedSessions, onHold, opResponseTime, operatorResponses,
                sessionTransferIn, sessionTransferOut, sessionTransferOutNoMessages,
                closedWithNoMessages, timeoutNoMessages, agentTimeout,
                userTimeout, fromQueueAsignToOpAssigned, fromSessionStartToOpFirstResponse,
                fromQueueAsignToOpFirstResponse, fromOpAssignedToOpFirstResponse,
                fromQueueAsignToSessionClosed, fromOpAssignationToSessionClosed,
                sessionTimeout, conversationLink
              )
              VALUES (
                src.tenant_id, src.sessionId, src.chatId, src.sessionCreationTime,
                src.avgAttendingTime, src.avgResponseTime, src.queue, src.agentName,
                src.agentId, src.typification, src.closedTime, src.openSessions,
                src.closedSessions, src.onHold, src.opResponseTime, src.operatorResponses,
                src.sessionTransferIn, src.sessionTransferOut, src.sessionTransferOutNoMessages,
                src.closedWithNoMessages, src.timeoutNoMessages, src.agentTimeout,
                src.userTimeout, src.fromQueueAsignToOpAssigned, src.fromSessionStartToOpFirstResponse,
                src.fromQueueAsignToOpFirstResponse, src.fromOpAssignedToOpFirstResponse,
                src.fromQueueAsignToSessionClosed, src.fromOpAssignationToSessionClosed,
                src.sessionTimeout, src.conversationLink
              );
            """,
            # Valores a insertar / actualizar
            TENANT_ID,
            s.get("sessionId"),
            s.get("chatId"),
            parse_ts(s.get("sessionCreationTime")),
            s.get("avgAttendingTime"),
            s.get("avgResponseTime"),
            s.get("queue"),
            s.get("agentName"),
            s.get("agentId"),
            s.get("typification"),
            parse_ts(s.get("closedTime")),
            s.get("openSessions"),
            s.get("closedSessions"),
            s.get("onHold"),
            s.get("opResponseTime"),
            s.get("operatorResponses"),
            s.get("sessionTransferIn"),
            s.get("sessionTransferOut"),
            s.get("sessionTransferOutNoMessages"),
            s.get("closedWithNoMessages"),
            s.get("timeoutNoMessages"),
            s.get("agentTimeout"),
            s.get("userTimeout"),
            s.get("fromQueueAsignToOpAssigned"),
            s.get("fromSessionStartToOpFirstResponse"),
            s.get("fromQueueAsignToOpFirstResponse"),
            s.get("fromOpAssignedToOpFirstResponse"),
            s.get("fromQueueAsignToSessionClosed"),
            s.get("fromOpAssignationToSessionClosed"),
            s.get("sessionTimeout"),
            s.get("conversationLink")
        )
        count += 1

    # Actualiza last_ts con to_dt
    if all_items:
        set_last_ts(cur, "agent-metrics", to_dt)
        logger.info("✔ agent_metrics: %d filas procesadas, last_ts actualizado a %s", count, to_dt)
    else:
        logger.info("— No hay nuevos registros en agent_metrics.")
        cur.commit()


# ——————————————————————————————————————————————————————————————
# ETL: MESSAGES + SUBTABLAS
# ——————————————————————————————————————————————————————————————

def etl_messages(cur: pyodbc.Cursor) -> None:
    """
    ETL para messages y sus subtablas:
      - chats
      - messages
      - message_content
      - message_buttons
      - message_carouselItems
      - message_media
      - message_files
      - message_location
      - message_call
      - encryptionParams
    Aplica MERGE o IF NOT EXISTS según corresponda.
    """
    logger.info("▶ ETL dbo.messages + subtablas")
    last = get_last_ts(cur, "messages")
    from_dt, to_dt = get_window(last)

    if from_dt >= to_dt:
        logger.info("— Ventana messages vacía; no hay rango nuevo.")
        return

    logger.debug("Ventana messages: %s → %s", from_dt, to_dt)
    params = {
        "from":             iso_z_ms(from_dt),
        "to":               iso_z_ms(to_dt),
        "limit":            1500,
        "long-term-search": True
    }
    data = fetch_all(URL_MESSAGES, params)
    logger.info("→ %d mensajes obtenidos", len(data))

    # Asegura tenant
    cur.execute(
        "IF NOT EXISTS(SELECT 1 FROM dbo.tenants WHERE tenant_id = ?) "
        "INSERT INTO dbo.tenants(tenant_id, tenant_name) VALUES(?, ?)",
        TENANT_ID, TENANT_ID, TENANT_ID
    )
    cur.commit()

    count = 0
    for m in data:
        mid     = m["id"]
        ts      = parse_ts(m.get("creationTime"))
        chat    = m.get("chat", {})
        chat_id = chat.get("chatId")
        chan    = chat.get("channelId")
        contact = chat.get("contactId")

        # Chats (si no existe, lo crea)
        #cur.execute(
        #    "IF NOT EXISTS(SELECT 1 FROM dbo.chats WHERE tenant_id = ? AND chatId = ?) "
        #    "INSERT INTO dbo.chats(tenant_id, chatId, channelId, contactId) VALUES(?, ?, ?, ?)",
        #    TENANT_ID, chat_id,
        #    TENANT_ID, chat_id, chan, contact
        #)

        # Chats (PK: tenant_id, chatId) con channelId y contactId
        cur.execute("""
            MERGE dbo.chats AS target
            USING (VALUES(?, ?, ?, ?)) AS src(tenant_id, chatId, channelId, contactId)
              ON target.tenant_id = src.tenant_id AND target.chatId = src.chatId
            WHEN MATCHED THEN
              UPDATE SET channelId = src.channelId, contactId = src.contactId
            WHEN NOT MATCHED THEN
              INSERT(tenant_id, chatId, channelId, contactId)
              VALUES(src.tenant_id, src.chatId, src.channelId, src.contactId);
        """,
        TENANT_ID, chat_id, chan, contact
        )

        # MESSAGES (MERGE en PK: tenant_id, id)
        cur.execute("""
            MERGE dbo.messages AS target
            USING (SELECT
                      ? AS tenant_id,
                      ? AS id,
                      ? AS creationTime,
                      ? AS [from],
                      ? AS agentId,
                      ? AS queueId,
                      ? AS sessionCreationTime,
                      ? AS chatId,
                      ? AS sessionId,
                      ? AS whatsAppTemplateName
                   ) AS src
            ON target.tenant_id = src.tenant_id
           AND target.id        = src.id
            WHEN MATCHED THEN
              UPDATE SET
                creationTime         = src.creationTime,
                [from]               = src.[from],
                agentId              = src.agentId,
                queueId              = src.queueId,
                sessionCreationTime  = src.sessionCreationTime,
                chatId               = src.chatId,
                sessionId            = src.sessionId,
                whatsAppTemplateName = src.whatsAppTemplateName
            WHEN NOT MATCHED THEN
              INSERT (
                tenant_id, id, creationTime, [from],
                agentId, queueId, sessionCreationTime,
                chatId, sessionId, whatsAppTemplateName
              )
              VALUES (
                src.tenant_id, src.id, src.creationTime, src.[from],
                src.agentId, src.queueId, src.sessionCreationTime,
                src.chatId, src.sessionId, src.whatsAppTemplateName
              );
        """,
        TENANT_ID, mid, ts, m.get("from"), m.get("agentId"),
        m.get("queueId"), parse_ts(m.get("sessionCreationTime")),
        chat_id, m.get("sessionId"),
        m.get("content", {}).get("whatsAppTemplateName")
        )

        # MESSAGE_CONTENT (MERGE en PK: tenant_id, messageId)
        c = m.get("content", {})
        cur.execute("""
            MERGE dbo.message_content AS target
            USING (SELECT
                      ? AS tenant_id,
                      ? AS messageId,
                      ? AS [type],
                      ? AS text,
                      ? AS selectedButton,
                      ? AS originalText,
                      ? AS originalAudioUrl
                   ) AS src
            ON target.tenant_id = src.tenant_id
           AND target.messageId = src.messageId
            WHEN MATCHED THEN
              UPDATE SET
                [type]            = src.[type],
                text              = src.text,
                selectedButton    = src.selectedButton,
                originalText      = src.originalText,
                originalAudioUrl  = src.originalAudioUrl
            WHEN NOT MATCHED THEN
              INSERT (
                tenant_id, messageId, [type],
                text, selectedButton, originalText, originalAudioUrl
              ) VALUES (
                src.tenant_id, src.messageId, src.[type],
                src.text, src.selectedButton, src.originalText, src.originalAudioUrl
              );
        """,
        TENANT_ID, mid,
        c.get("type"), c.get("text"),
        c.get("selectedButton"),
        c.get("originalText"),
        c.get("originalAudioUrl")
        )

        # MESSAGE_BUTTONS (PK: tenant_id, messageId, button)
        for btn in c.get("buttons", []):
            cur.execute(
                "IF NOT EXISTS(SELECT 1 FROM dbo.message_buttons "
                "WHERE tenant_id = ? AND messageId = ? AND button = ?) "
                "INSERT INTO dbo.message_buttons(tenant_id, messageId, button) VALUES(?, ?, ?)",
                TENANT_ID, mid, btn,
                TENANT_ID, mid, btn
            )

        # MESSAGE_CAROUSELITEMS (PK: tenant_id, messageId, itemIndex; evitamos duplicados verificando carouselItem)
        for item in c.get("carouselItems", []):
            cur.execute(
                "IF NOT EXISTS(SELECT 1 FROM dbo.message_carouselItems "
                "WHERE tenant_id = ? AND messageId = ? AND carouselItem = ?) "
                "INSERT INTO dbo.message_carouselItems(tenant_id, messageId, carouselItem) VALUES(?, ?, ?)",
                TENANT_ID, mid, item,
                TENANT_ID, mid, item
            )

        # MESSAGE_MEDIA (PK: tenant_id, mediaId; evitamos duplicados verificando url único)
        media = c.get("media")
        if media:
            url     = media.get("url")
            caption = media.get("caption")

            # Metadata en message_media (si no existe)
            cur.execute(
                "IF NOT EXISTS(SELECT 1 FROM dbo.message_media WHERE tenant_id = ? AND url = ?) "
                "INSERT INTO dbo.message_media(tenant_id, messageId, caption, url) VALUES(?, ?, ?, ?)",
                TENANT_ID, url,
                TENANT_ID, mid, caption, url
            )

            # Descarga o registra falla
            path, dl_status = download_and_store(url, TENANT_ID, mid, "media")
            db_path = path or _placeholder_path(TENANT_ID, mid, "media")

            # Upsert SIEMPRE en message_files (file_path NO puede ser NULL)
            cur.execute("""
                MERGE dbo.message_files AS target
                USING (SELECT ? AS tenant_id, ? AS messageId, 'media' AS file_type) AS src
                ON  target.tenant_id = src.tenant_id
                AND target.messageId = src.messageId
                AND target.file_type = src.file_type
                WHEN MATCHED THEN
                UPDATE SET
                    original_url  = ?,
                    file_path     = ?,               
                    downloaded_at = ?,
                    status        = ?
                WHEN NOT MATCHED THEN
                INSERT (tenant_id, messageId, file_type, original_url, file_path, downloaded_at, status)
                VALUES (src.tenant_id, src.messageId, src.file_type, ?, ?, ?, ?);
            """,
            # UPDATE
            TENANT_ID, mid, url, db_path, datetime.now(timezone.utc), dl_status,
            # INSERT
            url, db_path, datetime.now(timezone.utc), dl_status
            )


        # MESSAGE_LOCATION (PK: tenant_id, messageId)
        loc = c.get("location")
        if loc:
            cur.execute(
                "IF NOT EXISTS(SELECT 1 FROM dbo.message_location WHERE tenant_id = ? AND messageId = ?) "
                "INSERT INTO dbo.message_location(tenant_id, messageId, latitude, longitude, name, address) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                TENANT_ID, mid,
                TENANT_ID, mid,
                loc.get("latitude"), loc.get("longitude"), loc.get("name"), loc.get("address")
            )

        # MESSAGE_CALL (PK: tenant_id, messageId)
        call = c.get("call")
        if call:
            cur.execute(
                "IF NOT EXISTS(SELECT 1 FROM dbo.message_call WHERE tenant_id = ? AND messageId = ?) "
                "INSERT INTO dbo.message_call(tenant_id, messageId, [event]) VALUES(?, ?, ?)",
                TENANT_ID, mid,
                TENANT_ID, mid, call.get("event")
            )

        # ORIGINAL AUDIO (PK: tenant_id, messageId, file_type = 'audio')
        audio_url = c.get("originalAudioUrl")
        if audio_url:
            path, dl_status = download_and_store(audio_url, TENANT_ID, mid, "audio")
            db_path = path or _placeholder_path(TENANT_ID, mid, "audio")

            cur.execute("""
                MERGE dbo.message_files AS target
                USING (SELECT ? AS tenant_id, ? AS messageId, 'audio' AS file_type) AS src
                ON  target.tenant_id = src.tenant_id
                AND target.messageId = src.messageId
                AND target.file_type = src.file_type
                WHEN MATCHED THEN
                UPDATE SET
                    original_url  = ?,
                    file_path     = ?,              -- placeholder si falló
                    downloaded_at = ?,
                    status        = ?
                WHEN NOT MATCHED THEN
                INSERT (tenant_id, messageId, file_type, original_url, file_path, downloaded_at, status)
                VALUES (src.tenant_id, src.messageId, src.file_type, ?, ?, ?, ?);
            """,
            # UPDATE
            TENANT_ID, mid, audio_url, db_path, datetime.now(timezone.utc), dl_status,
            # INSERT
            audio_url, db_path, datetime.now(timezone.utc), dl_status
            )

        # ENCRYPTION_PARAMS (PK: tenant_id, messageId)
        ep = m.get("encryptionParams", {})
        if ep:
            cur.execute(
                "IF NOT EXISTS(SELECT 1 FROM dbo.encryptionParams WHERE tenant_id = ? AND messageId = ?) "
                "INSERT INTO dbo.encryptionParams(tenant_id, messageId, version, configId, [timestamp], encryptedKey) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                TENANT_ID, mid,
                TENANT_ID, mid,
                ep.get("version"), ep.get("configId"), ep.get("timestamp"), ep.get("encryptedKey")
            )

        count += 1

    # Actualiza last_ts con to_dt
    if data:
        set_last_ts(cur, "messages", to_dt)
        logger.info("✔ messages + subtablas: %d mensajes procesados, last_ts actualizado a %s", count, to_dt)
    else:
        logger.info("— No hay nuevos mensajes que procesar.")
        cur.commit()


# ——————————————————————————————————————————————————————————————
# ETL: CHAT_DETAILS + VARIABLES + TAGS
# ——————————————————————————————————————————————————————————————

def etl_chat_details(cur: pyodbc.Cursor) -> None:
    """
    ETL para chat_details y tablas relacionadas:
      - chat_details (PK: tenant_id, chatId)
      - chat_variables (PK: tenant_id, chatId, var_key)
      - chat_tags (PK: tenant_id, chatId, tag)
    Sólo procesa chats que no estén en chat_details.
    """
    logger.info("▶ ETL dbo.chat_details + vars + tags")

    # Obtiene chatId que no tienen detalles aún
    cur.execute("""
        SELECT c.chatId
        FROM dbo.chats c
        LEFT JOIN dbo.chat_details d
          ON c.tenant_id = d.tenant_id AND c.chatId = d.chatId
        WHERE c.tenant_id = ? AND d.chatId IS NULL
    """, TENANT_ID)
    missing = [r.chatId for r in cur.fetchall()]
    logger.info("→ %d chats pendientes de chat_details", len(missing))

    count = 0
    for cid in missing:
        resp = api_request("GET", URL_CHAT.format(cid))
        chat = resp.json().get("chat", {})

        # Debug: mostrar si Botmaker trae variables/tags
        logger.debug("  → Datos chat %s: variables=%s, tags=%s",
                     cid, chat.get("variables"), chat.get("tags"))

        # Inserta chat_details
        cur.execute(
            "INSERT INTO dbo.chat_details("
            "tenant_id, chatId, creationTime, lastSessionCreationTime, externalId, "
            "firstName, lastName, country, email, whatsAppWindowCloseDatetime, "
            "queueId, agentId, onHoldAgentId, lastUserMessageDatetime, isTester, isBotMuted, isBanned"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            TENANT_ID, chat.get("chatId"),
            parse_ts(chat.get("creationTime")),
            parse_ts(chat.get("lastSessionCreationTime")),
            chat.get("externalId"),
            chat.get("firstName"),
            chat.get("lastName"),
            chat.get("country"),
            chat.get("email"),
            parse_ts(chat.get("whatsAppWindowCloseDatetime")),
            chat.get("queueId"),
            chat.get("agentId"),
            chat.get("onHoldAgentId"),
            parse_ts(chat.get("lastUserMessageDatetime")),
            int(chat.get("isTester", False)),
            int(chat.get("isBotMuted", False)),
            int(chat.get("isBanned", False))
        )

        # Inserta variables (PK: tenant_id, chatId, var_key)
        for key, val in (chat.get("variables") or {}).items():
            cur.execute(
                "IF NOT EXISTS(SELECT 1 FROM dbo.chat_variables "
                "WHERE tenant_id = ? AND chatId = ? AND var_key = ?) "
                "INSERT INTO dbo.chat_variables(tenant_id, chatId, var_key, var_value) VALUES(?, ?, ?, ?)",
                TENANT_ID, cid, key,
                TENANT_ID, cid, key, val
            )

        # Inserta tags (PK: tenant_id, chatId, tag)
        for tag in chat.get("tags", []):
            cur.execute(
                "IF NOT EXISTS(SELECT 1 FROM dbo.chat_tags "
                "WHERE tenant_id = ? AND chatId = ? AND tag = ?) "
                "INSERT INTO dbo.chat_tags(tenant_id, chatId, tag) VALUES(?, ?, ?)",
                TENANT_ID, cid, tag,
                TENANT_ID, cid, tag
            )

        count += 1
        
    cur.commit()
    logger.info("✔ chat_details + vars + tags: insertados %d chats", count)

# ——————————————————————————————————————————————————————————————
# FUNCIONES AUXILIARES
# ——————————————————————————————————————————————————————————————

# Helper: para algunos tenants, el temp-link funciona mejor
# si usamos file-url sin "storage.googleapis.com".
def _alt_file_url(original: str) -> str | None:
    try:
        # Caso típico: https://storage.googleapis.com/storage.botmaker.com/<PATH>
        marker = "storage.googleapis.com/storage.botmaker.com/"
        if marker in original:
            path = original.split(marker, 1)[1]
            return f"https://storage.botmaker.com/{path}"
        # Otra variante posible: https://storage.googleapis.com/<bucket>/<PATH>
        parsed = urlparse(original)
        if parsed.netloc == "storage.googleapis.com" and parsed.path.startswith("/storage.botmaker.com/"):
            return "https://storage.botmaker.com/" + parsed.path.lstrip("/storage.botmaker.com/").lstrip("/")
    except Exception:
        pass
    return None

# Helper: pide a Botmaker una URL temporal firmada para un media privado. 
# Intenta con la file-url original y, si falla, prueba una variante alternativa.
def get_temp_link(file_url: str, expire_minutes: int = 10) -> str | None:
    def _ask(u: str) -> tuple[int, str | None, str]:
        resp = requests.get(
            "https://api.botmaker.com/v2.0/private-media/temp-access-link",
            headers={"access-token": BOTMAKER_TOKEN, "Accept": "application/json"},
            params={"file-url": u, "expire-minutes": expire_minutes},
            timeout=15,
        )
        if resp.status_code == 200:
            # 1) JSON {"tempUrl": "..."} o {"url": "..."}
            try:
                data = resp.json()
                tmp = data.get("tempUrl") or data.get("url")
                if tmp:
                    return 200, tmp, ""
            except ValueError:
                # 2) Algunos tenants devuelven texto plano con la URL
                txt = (resp.text or "").strip()
                if txt.startswith("http"):
                    return 200, txt, ""
            # 3) 200 sin URL utilizable → devolvemos body para log opcional
            return 200, None, (resp.text or "")[:500]
        # No 200 → devolvemos body para log opcional
        return resp.status_code, None, (resp.text or "")[:500]

    # 1) intento con la URL original
    code, temp, body = _ask(file_url)
    if code == 200 and temp:
        return temp
    if code != 200:
        if LOG_HTTP_BODY:
            logger.warning("Temp-link fallo HTTP %s. Body: %s", code, body)
        else:
            logger.warning("Temp-link fallo HTTP %s.", code)
    else:
        if LOG_HTTP_BODY:
            logger.warning("Temp-link 200 pero sin URL utilizable. Payload: %s", body)
        else:
            logger.warning("Temp-link 200 pero sin URL utilizable.")

    # 2) intento con file-url alternativa (si aplica)
    alt = _alt_file_url(file_url)
    if alt:
        code2, temp2, body2 = _ask(alt)
        if code2 == 200 and temp2:
            logger.info("Temp-link obtenido usando file-url alternativa.")
            return temp2
        if code2 != 200:
            if LOG_HTTP_BODY:
                logger.warning("Temp-link (alternativa) fallo HTTP %s. Body: %s", code2, body2)
            else:
                logger.warning("Temp-link (alternativa) fallo HTTP %s.", code2)
        else:
            if LOG_HTTP_BODY:
                logger.warning("Temp-link 200 (alternativa) sin URL utilizable. Payload: %s", body2)
            else:
                logger.warning("Temp-link 200 (alternativa) sin URL utilizable.")

    return None

    
def download_and_store(url: str, tenant_id: str, message_id: str, kind: str) -> tuple[str | None, str]:
    """
    Descarga un recurso (media, audio, video, imagen, etc.) a disco y retorna la ruta RELATIVA
    a partir de “C:\\KoalaETL”. Quedará algo así:
      files\\<tenant_id>\\<message_id>\\<kind>\\<nombre_archivo>

    Devuelve (ruta_relativa|None, status) con:
      status ∈ {'ok','forbidden','not_found','error','skipped'}
    """
    if not url:
        return None, 'skipped'

    try:
        # 1) Primer intento con la URL ORIGINAL (muchos archivos siguen siendo públicos)
        resp = requests.get(url, stream=True, timeout=30, headers={"User-Agent": "KoalaETL/1.0"})

        # 2) Si es privada/expirada → pedimos temp-link y reintentamos
        if resp.status_code == 403:
            logger.info("403 Forbidden en descarga inicial, intentando regenerar URL temporal…")
            temp_url = get_temp_link(url, expire_minutes=10)
            if temp_url:
                resp = requests.get(temp_url, stream=True, timeout=30, headers={"User-Agent": "KoalaETL/1.0"})
            else:
                logger.warning("No se pudo regenerar firma temporal para: %s", url)
                return None, 'forbidden'

        # 3) 404 directo → no existe
        if resp.status_code == 404:
            logger.warning("No se puede descargar (404 Not Found): %s", url)
            return None, 'not_found'

        # 4) El CDN a veces responde 200 con JSON {"message":"No file found ..."}
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "application/json" in ctype:
            preview = (resp.text or "")[:300]
            if "no file found" in preview.lower():
                logger.warning("CDN devolvió 'No file found' para %s", url)
                return None, 'not_found'

        # 5) Otros errores HTTP
        resp.raise_for_status()

        # 6) Guardado en disco
        base_folder = Path(r"C:\KoalaETL\files") / tenant_id / message_id / kind
        base_folder.mkdir(parents=True, exist_ok=True)

        # Nombre de archivo: sacado de la URL original, con fallback
        filename = (url.split("/")[-1].split("?")[0] or f"{kind}_{message_id}")
        filepath_abs = base_folder / filename

        with open(filepath_abs, "wb") as f:
            for chunk in resp.iter_content(chunk_size=4096):
                if chunk:  # defensivo
                    f.write(chunk)

        rel_path = filepath_abs.relative_to(Path(r"C:\KoalaETL"))
        logger.debug("Recurso descargado correctamente: %s", url)
        return str(rel_path).replace("/", "\\"), 'ok'

    except requests.RequestException as e:
        # Errores de red, timeouts, etc.
        logger.warning("Recurso inaccesible (RequestException) %s (%s)", url, e)
        return None, 'error'
    except Exception as e:
        logger.error("Error descargando %s: %s", url, e)
        return None, 'error'

# ——————————————————————————————————————————————————————————————
# MAIN: ORQUESTADOR DE ETL
# ——————————————————————————————————————————————————————————————
def _run_stage(label: str, fn, cur) -> bool:
    try:
        fn(cur)
        return True  # ← éxito: habilita el commit de la etapa
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", None)
        if code == 429:
            logger.warning("Etapa %s saltada por rate-limit (429). Se reintentará en el próximo cron.", label)
        else:
            logger.exception("Etapa %s falló (HTTP %s). Continúo con las siguientes.", label, code)
        return False  # ← falló: no cometer
    except Exception:
        logger.exception("Etapa %s falló por error no controlado. Continúo con las siguientes.", label)
        return False  # ← falló: no cometer

def main() -> None:
    conn = get_connection()
    cur  = conn.cursor()

    # Asegura que exista la tabla de control (si la crea, conviene persistir)
    ensure_etl_control_table(cur)
    try:
        conn.commit()
    except Exception:
        pass  # por si no hubo cambios

    try:
        # ETL de tenant estático (asegura que exista la entrada en tenants)
        if _run_stage("tenant/agents/queues", etl_tenant_agent_queue, cur):
            conn.commit()

        # ETL de agent_performance y tablas relacionadas
        if _run_stage("agent_performance", etl_agent_performance, cur):
            conn.commit()

        # ETL de agent_metrics
        if _run_stage("agent_metrics", etl_agent_metrics, cur):
            conn.commit()

        # ETL de messages y subtablas
        if _run_stage("messages", etl_messages, cur):
            conn.commit()

        # ETL de chat_details y subtablas
        if _run_stage("chat_details", etl_chat_details, cur):
            conn.commit()
    finally:
        conn.close()
        logger.info("Proceso ETL completado.")

if __name__ == "__main__":
    main()