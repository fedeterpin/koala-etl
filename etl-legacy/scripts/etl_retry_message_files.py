#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import logging
import argparse
import requests
import pyodbc
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from urllib.parse import quote, urlparse

# ——————————————————————————————————————————————————————————————
# [1] Configuración y Logger (idéntico estilo al ETL principal)
# ——————————————————————————————————————————————————————————————

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "config" / ".env")

# Flags
DEBUGGER = os.getenv("DEBUGGER", "False").lower() in ("1", "true", "yes")
LOG_HTTP_BODY = os.getenv("LOG_HTTP_BODY", "False").lower() in ("1", "true", "yes")

# Logger para reintentos (archivo aparte para análisis)
logger = logging.getLogger("KoalaETL.retry")
logger.setLevel(logging.DEBUG if DEBUGGER else logging.INFO)

fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

sh = logging.StreamHandler(sys.stdout)
sh.setLevel(logging.DEBUG if DEBUGGER else logging.INFO)
sh.setFormatter(fmt)
logger.addHandler(sh)

logs_dir = BASE_DIR / "logs"
logs_dir.mkdir(parents=True, exist_ok=True)
fh = logging.FileHandler(logs_dir / "koala_etl_retry.log", encoding="utf-8")
fh.setLevel(logging.DEBUG if DEBUGGER else logging.INFO)
fh.setFormatter(fmt)
logger.addHandler(fh)

# ——————————————————————————————————————————————————————————————
# [2] Parámetros/Conexión
# ——————————————————————————————————————————————————————————————

# DB
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

def get_connection() -> pyodbc.Connection:
    return pyodbc.connect(CONN_STR)

# Botmaker (para pedir temp-links si hace falta)
BOTMAKER_TOKEN = os.getenv("BOTMAKER_TOKEN")

# Allowed status (coincide con el CHECK de la tabla)
ALLOWED_STATUSES = {"ok", "forbidden", "not_found", "error", "skipped"}

def safe_status(st: str | None) -> str:
    """
    Normaliza cualquier status al set permitido.
    """
    s = (st or "").strip().lower()
    if s in ALLOWED_STATUSES:
        return s
    return "error"

# ——————————————————————————————————————————————————————————————
# [3] Helpers descarga (misma lógica que el ETL principal)
# ——————————————————————————————————————————————————————————————

def _placeholder_path(tenant_id: str, message_id: str, kind: str) -> str:
    return f"files\\{tenant_id}\\{message_id}\\{kind}\\(not-downloaded)"

def _alt_file_url(original: str) -> str | None:
    """
    Para algunos tenants el temp-link funciona mejor si la file-url
    es 'https://storage.botmaker.com/<path>' en vez de GCS directo.
    """
    try:
        marker = "storage.googleapis.com/storage.botmaker.com/"
        if marker in original:
            path = original.split(marker, 1)[1]
            return f"https://storage.botmaker.com/{path}"
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
            try:
                data = resp.json()
                tmp = data.get("tempUrl") or data.get("url")
                if tmp:
                    return 200, tmp, ""
            except ValueError:
                txt = (resp.text or "").strip()
                if txt.startswith("http"):
                    return 200, txt, ""
            return 200, None, (resp.text or "")[:500]
        return resp.status_code, None, (resp.text or "")[:500]

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
    Descarga un recurso a disco y retorna (ruta_relativa|None, status).
    Status ∈ {'ok','forbidden','not_found','error','skipped'}.
    """
    if not url:
        return None, 'skipped'

    try:
        # 1) Primer intento con la URL ORIGINAL
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

        # 4) A veces 200 con JSON de error del CDN
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "application/json" in ctype:
            preview = (resp.text or "")[:300]
            if "no file found" in preview.lower():
                logger.warning("CDN devolvió 'No file found' para %s", url)
                return None, 'not_found'

        # 5) Otros errores HTTP
        resp.raise_for_status()

        # 6) Guardado
        base_folder = Path(r"C:\KoalaETL\files") / tenant_id / message_id / kind
        base_folder.mkdir(parents=True, exist_ok=True)

        filename = (url.split("/")[-1].split("?")[0] or f"{kind}_{message_id}")
        filepath_abs = base_folder / filename

        with open(filepath_abs, "wb") as f:
            for chunk in resp.iter_content(chunk_size=4096):
                if chunk:
                    f.write(chunk)

        rel_path = filepath_abs.relative_to(Path(r"C:\KoalaETL"))
        logger.debug("Recurso descargado correctamente: %s", url)
        return str(rel_path).replace("/", "\\"), 'ok'

    except requests.RequestException as e:
        logger.warning("Recurso inaccesible (RequestException) %s (%s)", url, e)
        return None, 'error'
    except Exception as e:
        logger.error("Error descargando %s: %s", url, e)
        return None, 'error'

# ——————————————————————————————————————————————————————————————
# [4] Mini-reporte antes/después (conteos)
# ——————————————————————————————————————————————————————————————

def snapshot_counts(cur: pyodbc.Cursor, tenant_id: str) -> list[tuple[str, str, int]]:
    """
    Devuelve [(status, file_type, cnt), ...] para un tenant.
    """
    cur.execute("""
        SELECT status, file_type, COUNT(*) AS cnt
        FROM dbo.message_files
        WHERE tenant_id = ?
        GROUP BY status, file_type
        ORDER BY status, file_type;
    """, tenant_id)
    return [(r.status, r.file_type, r.cnt) for r in cur.fetchall()]

def print_snapshot(title: str, rows: list[tuple[str, str, int]]) -> None:
    logger.info("%s", title)
    if not rows:
        logger.info("(sin filas)")
        return
    for st, ft, cnt in rows:
        logger.info("  - %-10s | %-8s | %d", st, ft, cnt)

# ——————————————————————————————————————————————————————————————
# [5] Reproceso por lote
# ——————————————————————————————————————————————————————————————

def reprocess_batch(
    cur: pyodbc.Cursor,
    tenant_id: str,
    statuses: list[str],
    file_types: list[str] | None,
    limit: int,
    commit_every: int = 50
) -> None:

    statuses = [s.strip().lower() for s in statuses if s.strip()]
    if file_types:
        file_types = [t.strip().lower() for t in file_types if t.strip()]

    # Construcción dinámica del WHERE
    where = ["tenant_id = ?"]
    params: list = [tenant_id]

    if statuses:
        where.append(f"status IN ({','.join(['?']*len(statuses))})")
        params.extend(statuses)

    if file_types:
        where.append(f"LOWER(file_type) IN ({','.join(['?']*len(file_types))})")
        params.extend(file_types)

    sql = f"""
        SELECT TOP ({limit})
            tenant_id, messageId, file_type, original_url, file_path, status
        FROM dbo.message_files
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(downloaded_at, '1900-01-01'), messageId
    """

    cur.execute(sql, params)
    rows = cur.fetchall()
    if not rows:
        logger.info("No hay filas para reprocesar con los filtros dados.")
        return

    logger.info("Reprocesando %d filas…", len(rows))

    processed = 0
    for r in rows:
        tnt   = r.tenant_id
        mid   = r.messageId
        ftype = r.file_type
        url   = r.original_url

        try:
            path, dl_status = download_and_store(url, tnt, mid, ftype)
            db_path = path or _placeholder_path(tnt, mid, ftype)
            dl_status_norm = safe_status(dl_status)

            cur.execute(
                """
                UPDATE dbo.message_files
                   SET file_path     = ?,
                       downloaded_at = ?,
                       status        = ?
                 WHERE tenant_id = ? AND messageId = ? AND file_type = ?
                """,
                db_path, datetime.now(timezone.utc), dl_status_norm,
                tnt, mid, ftype
            )

            processed += 1
            if processed % commit_every == 0:
                cur.commit()
                logger.debug("Commit parcial (%d)…", processed)

        except Exception as e:
            # Log de error por fila, sin tumbar el proceso de lote
            logger.error("Fallo reprocesando messageId=%s tipo=%s: %s", mid, ftype, e, exc_info=DEBUGGER)

    # Commit final
    cur.commit()
    logger.info("✔ Lote terminado. Filas procesadas: %d", processed)

# ——————————————————————————————————————————————————————————————
# [6] CLI
# ——————————————————————————————————————————————————————————————

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reintenta descargar archivos de dbo.message_files (media/audio/document/video/image)."
    )
    parser.add_argument("--tenant", default=os.getenv("TENANT_ID"),
                        help="Tenant a procesar (por defecto, TENANT_ID del .env).")
    parser.add_argument("--statuses", default="forbidden,not_found,error",
                        help="Lista de estados a reintentar, separados por coma. "
                             "Ej: forbidden,not_found,error")
    parser.add_argument("--file-types", default="media,audio,document,video,image",
                        help="Tipos de archivo a incluir, separados por coma. Vacío para todos.")
    parser.add_argument("--limit", type=int, default=200,
                        help="Máximo de filas a procesar en este lote.")
    parser.add_argument("--commit-every", type=int, default=50,
                        help="Commit parcial cada N filas.")
    parser.add_argument("--report", action="store_true",
                        help="Muestra snapshot de conteos antes y después del reintento.")
    return parser.parse_args()

# ——————————————————————————————————————————————————————————————
# [7] Main
# ——————————————————————————————————————————————————————————————

def main() -> None:
    args = parse_args()

    if not args.tenant:
        logger.error("TENANT_ID no especificado (ni por --tenant ni en .env).")
        sys.exit(1)

    statuses = [s.strip() for s in (args.statuses or "").split(",") if s.strip()]
    ftypes = [t.strip() for t in (args.file_types or "").split(",") if t.strip()]
    if not ftypes:
        ftypes = None  # todos

    conn = get_connection()
    cur = conn.cursor()

    try:
        # Snapshot previo
        if args.report:
            before = snapshot_counts(cur, args.tenant)
            print_snapshot("📊 Snapshot ANTES del reintento:", before)

        # Reproceso
        reprocess_batch(
            cur,
            tenant_id=args.tenant,
            statuses=statuses,
            file_types=ftypes,
            limit=args.limit,
            commit_every=args.commit_every
        )

        # Snapshot posterior
        if args.report:
            after = snapshot_counts(cur, args.tenant)
            print_snapshot("📊 Snapshot DESPUÉS del reintento:", after)

    except Exception as e:
        logger.exception("Error no controlado en el reproceso: %s", e)
    finally:
        conn.close()
        logger.info("Proceso de reintento completado.")

if __name__ == "__main__":
    main()
