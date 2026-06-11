"""Cliente HTTP de Botmaker por tenant (port de etl_botmaker_logs.py).

Respeta las notas de la API (PLAN-APP.md §3):
- Base v2.0 con header `access-token` (no Bearer).
- Throttle ≥1.2 s entre requests por tenant; backoff exponencial con jitter en
  429 (respetando Retry-After) y 5xx; reintento tras 401 con refresh.
- El refresh token ROTA en cada refresh (§11.1): `on_tokens_rotated` debe
  persistirlo inmediatamente o el tenant queda deslogueado para siempre.
- El temp-link para media privada puede requerir la URL alternativa
  `https://storage.botmaker.com/<path>` (§11.4).
"""

import logging
import random
import time
from collections.abc import Callable
from urllib.parse import urlparse

import requests

logger = logging.getLogger("koala.worker.botmaker")

BOTMAKER_BASE_URL = "https://api.botmaker.com/v2.0"
URL_MESSAGES = f"{BOTMAKER_BASE_URL}/messages"
URL_AGENT_PERF = f"{BOTMAKER_BASE_URL}/dashboards/agent-performance"
URL_AGENT_METRICS = f"{BOTMAKER_BASE_URL}/dashboards/agent-metrics"
URL_CHAT = f"{BOTMAKER_BASE_URL}/chats/{{}}"
URL_TEMP_LINK = f"{BOTMAKER_BASE_URL}/private-media/temp-access-link"
URL_REFRESH = "https://go.botmaker.com/api/v1.0/auth/credentials"


def alt_file_url(original: str) -> str | None:
    """Variante https://storage.botmaker.com/<path> para temp-links (§11.4)."""
    try:
        marker = "storage.googleapis.com/storage.botmaker.com/"
        if marker in original:
            return "https://storage.botmaker.com/" + original.split(marker, 1)[1]
        parsed = urlparse(original)
        if parsed.netloc == "storage.googleapis.com" and parsed.path.startswith(
            "/storage.botmaker.com/"
        ):
            return "https://storage.botmaker.com/" + parsed.path.removeprefix(
                "/storage.botmaker.com/"
            ).lstrip("/")
    except Exception:
        pass
    return None


class BotmakerAuthError(Exception):
    pass


class BotmakerClient:
    def __init__(
        self,
        *,
        client_id: str,
        secret_id: str,
        access_token: str,
        refresh_token: str,
        on_tokens_rotated: Callable[[str, str], None],
        session: requests.Session | None = None,
        min_interval: float = 1.2,
        max_retries: int = 6,
        backoff_base: float = 1.7,
        jitter_max_ms: int = 120,
        timeout: int = 30,
    ):
        self.client_id = client_id
        self.secret_id = secret_id
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.on_tokens_rotated = on_tokens_rotated
        self.session = session or requests.Session()
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.jitter_max_ms = jitter_max_ms
        self.timeout = timeout
        self._last_call_ts = 0.0

    # ——— throttle / backoff ———

    def _sleep_with_jitter(self, base: float) -> None:
        time.sleep(base + random.randint(0, self.jitter_max_ms) / 1000.0)

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call_ts
        if elapsed < self.min_interval:
            self._sleep_with_jitter(self.min_interval - elapsed)

    @property
    def _headers(self) -> dict:
        return {"Accept": "application/json", "access-token": self.access_token}

    # ——— refresh de credenciales (v1.0) ———

    def refresh_credentials(self) -> None:
        resp = self.session.post(
            URL_REFRESH,
            headers={
                "Accept": "application/json",
                "clientId": self.client_id,
                "secretId": self.secret_id,
                "refreshToken": self.refresh_token,
            },
            timeout=self.timeout,
        )
        if resp.status_code == 204:
            logger.info("Refresh respondió 204: sin cambio de credenciales")
            return
        if resp.status_code == 200:
            data = resp.json()
            new_token = data.get("accessToken") or data.get("access_token")
            new_refresh = data.get("refreshToken") or data.get("refresh_token")
            if not new_token or not new_refresh:
                raise BotmakerAuthError(f"Refresh sin campos válidos: {list(data)}")
            self.access_token = new_token
            self.refresh_token = new_refresh
            # CRÍTICO: persistir el refresh token rotado inmediatamente (§11.1)
            self.on_tokens_rotated(new_token, new_refresh)
            logger.info("Token de Botmaker actualizado (refresh rotado y persistido)")
            return
        raise BotmakerAuthError(f"Refresh falló con HTTP {resp.status_code}")

    # ——— request con reintentos ———

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        r: requests.Response | None = None
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            r = self.session.request(
                method, url, headers=self._headers, timeout=self.timeout, **kwargs
            )

            if r.status_code == 401:
                logger.warning("401 de Botmaker: refrescando token")
                self.refresh_credentials()
                self._throttle()
                r = self.session.request(
                    method, url, headers=self._headers, timeout=self.timeout, **kwargs
                )

            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else max(
                        self.min_interval, self.backoff_base**attempt
                    )
                except ValueError:
                    wait = max(self.min_interval, self.backoff_base**attempt)
                logger.warning("429 Too Many Requests; espero %.2fs (%d/%d)",
                               wait, attempt, self.max_retries)
                self._sleep_with_jitter(wait)
                continue

            if 500 <= r.status_code < 600:
                wait = max(self.min_interval, self.backoff_base**attempt)
                logger.warning("HTTP %d en %s; reintento en %.2fs (%d/%d)",
                               r.status_code, url, wait, attempt, self.max_retries)
                self._sleep_with_jitter(wait)
                continue

            self._last_call_ts = time.monotonic()
            if r.status_code >= 400:
                if r.status_code == 400:
                    logger.error("HTTP 400 en %s (¿ventana > 1 mes?)", url)
                r.raise_for_status()
            return r

        if r is None:
            raise requests.HTTPError(f"Agotados reintentos para {method} {url}")
        r.raise_for_status()
        return r  # inalcanzable; para tipado

    def fetch_all(self, url: str, params: dict | None = None) -> list[dict]:
        """Pagina con `nextPage` y devuelve todos los items (claves data|items)."""
        items: list[dict] = []
        p = dict(params or {})
        next_url = url
        while next_url:
            resp = self.request("GET", next_url, params=p)
            if resp.status_code == 204 or not resp.text.strip():
                break
            try:
                j = resp.json()
            except ValueError:
                logger.warning("Respuesta sin JSON en %s; se detiene la paginación", next_url)
                break
            data = j.get("data") or j.get("items")
            if not data:
                break
            items.extend(data)
            next_page = j.get("nextPage")
            if not next_page:
                break
            p = {}  # nextPage ya trae los parámetros
            next_url = next_page
        return items

    # ——— media privada ———

    def get_temp_link(self, file_url: str, expire_minutes: int = 10) -> str | None:
        def _ask(u: str) -> str | None:
            resp = self.session.get(
                URL_TEMP_LINK,
                headers=self._headers,
                params={"file-url": u, "expire-minutes": expire_minutes},
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning("Temp-link falló con HTTP %s", resp.status_code)
                return None
            try:
                data = resp.json()
                return data.get("tempUrl") or data.get("url")
            except ValueError:
                txt = (resp.text or "").strip()
                return txt if txt.startswith("http") else None

        temp = _ask(file_url)
        if temp:
            return temp
        alt = alt_file_url(file_url)
        if alt:
            temp = _ask(alt)
            if temp:
                logger.info("Temp-link obtenido con la file-url alternativa")
                return temp
        return None

    def download(self, url: str) -> requests.Response:
        """GET directo de un archivo (sin headers de API: es el CDN)."""
        return self.session.get(
            url, stream=True, timeout=self.timeout, headers={"User-Agent": "KoalaETL/2.0"}
        )
