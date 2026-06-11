import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
import requests

# — Forzar UTF-8 en la consola Windows (a partir de Python 3.7) —
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# — Directorios —
SCRIPT_DIR  = os.path.dirname(__file__)
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
LOG_DIR     = os.path.join(PROJECT_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# — Configuración de logging —
log_file  = os.path.join(LOG_DIR, 'test_token_refresh.log')
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

console_h = logging.StreamHandler()
console_h.setFormatter(formatter)

file_h = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
file_h.setFormatter(formatter)

logger = logging.getLogger("TEST_REFRESH")
logger.setLevel(logging.INFO)
logger.addHandler(console_h)
logger.addHandler(file_h)

# — Carga de variables de entorno —
load_dotenv(os.path.join(PROJECT_DIR, 'config', '.env'))
CLIENT_ID     = os.getenv("BOTMAKER_CLIENT_ID")
SECRET_ID     = os.getenv("BOTMAKER_SECRET_ID")
TOKEN         = os.getenv("BOTMAKER_TOKEN")
REFRESH_TOKEN = os.getenv("BOTMAKER_REFRESH_TOKEN")

# — URLs de Botmaker según Swagger —
BASE_URL     = "https://api.botmaker.com/v2.0"
URL_MESSAGES = f"{BASE_URL}/messages"
# El endpoint de refresh está en el host go.botmaker.com bajo /api/v1.0/
URL_REFRESH  = "https://go.botmaker.com/api/v1.0/auth/credentials"

# — Headers iniciales —
HEADERS = {
    "Accept":       "application/json",
    "access-token": TOKEN
}

def refresh_api_credentials():
    """Refresca accessToken y refreshToken usando clientId/secretId."""
    global TOKEN, REFRESH_TOKEN, HEADERS
    hdr = {
        "Accept":       "application/json",
        "Content-Type": "application/json",
        "clientId":     CLIENT_ID,
        "secretId":     SECRET_ID,
        "refreshToken": REFRESH_TOKEN
    }
    resp = requests.post(URL_REFRESH, headers=hdr, timeout=10)
    if resp.status_code != 200:
        logger.error(f"ERROR al refrescar token [{resp.status_code}]: {resp.text}")
        resp.raise_for_status()
    data = resp.json()
    TOKEN         = data["accessToken"]
    REFRESH_TOKEN = data["refreshToken"]
    HEADERS["access-token"] = TOKEN
    logger.info("Token refrescado con éxito")

def api_request(method, url, **kwargs):
    """Envuelve requests.request, refresca token al 401 y reintenta."""
    r = requests.request(method, url, headers=HEADERS, **kwargs)
    if r.status_code == 401:
        logger.warning("401 recibido: refrescando token")
        refresh_api_credentials()
        r = requests.request(method, url, headers=HEADERS, **kwargs)
    r.raise_for_status()
    return r

if __name__ == "__main__":
    # 1) Primera petición válida
    logger.info(">> Primera petición a /messages?limit=1")
    r1 = api_request("GET", URL_MESSAGES, params={"limit": 1})
    logger.info(f"-> {r1.status_code}, items: {len(r1.json().get('items', []))}")

    # 2) Forzar 401 y refresco
    HEADERS["access-token"] = "TOKEN_INVALIDO"
    logger.info(">> Segunda petición (token inválido)")
    r2 = api_request("GET", URL_MESSAGES, params={"limit": 1})
    logger.info(f"-> Tras refresh: {r2.status_code}")
