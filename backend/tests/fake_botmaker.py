"""Botmaker falso para tests del worker: emula la API y el CDN con fixtures."""

import json as jsonlib

import requests


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, content=b"", headers=None, text=None):
        self.status_code = status_code
        self._json = json_data
        self.headers = headers or {}
        if json_data is not None:
            self.content = jsonlib.dumps(json_data).encode()
            self.headers.setdefault("Content-Type", "application/json")
        else:
            self.content = content
        self._text = text
        self.raw = None  # fuerza el camino put_object(content) en files.py

    @property
    def text(self):
        if self._text is not None:
            return self._text
        try:
            return self.content.decode()
        except UnicodeDecodeError:
            return ""

    def json(self):
        if self._json is None:
            raise ValueError("sin JSON")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class FakeBotmakerSession:
    """Sesión `requests` falsa. Registrar handlers con .route(method, matcher, fn)."""

    def __init__(self):
        self.routes: list[tuple[str, str, object]] = []  # (method, url_prefix, fn)
        self.calls: list[tuple[str, str, dict]] = []

    def route(self, method: str, url_prefix: str, fn) -> None:
        self.routes.append((method.upper(), url_prefix, fn))

    def request(self, method, url, headers=None, timeout=None, params=None, **kw):
        self.calls.append((method.upper(), url, params or {}))
        for m, prefix, fn in self.routes:
            if m == method.upper() and url.startswith(prefix):
                resp = fn(url, params or {}, headers or {})
                if resp is not None:
                    return resp
        return FakeResponse(404, json_data={"message": "ruta no mockeada", "url": url})

    def get(self, url, headers=None, timeout=None, params=None, stream=False, **kw):
        return self.request("GET", url, headers=headers, params=params)

    def post(self, url, headers=None, timeout=None, **kw):
        return self.request("POST", url, headers=headers)


PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"
WAV = b"RIFFfake-audio-bytes"

AGENT_PERFORMANCE = [{
    "agentEmail": "etl-agent@tetl.com",
    "agentName": "Agente ETL",
    "role": "agent",
    "state": "online",
    "checkin": "2026-05-01T09:00:00Z",
    "checkout": "2026-05-01T17:00:00Z",
    "queue": ["Siniestros", "Ventas"],
}]

AGENT_METRICS_OPEN = [{
    "sessionId": "etl-s-open",
    "chatId": "5493300000001",
    "sessionCreationTime": "2026-05-02T10:00:00Z",
    "queue": "Siniestros",
    "agentName": None,
    "agentId": None,
    "fromOpAssignedToOpFirstResponse": None,
    "openSessions": 1,
    "closedSessions": 0,
}]

AGENT_METRICS_CLOSED = [{
    "sessionId": "etl-s-closed",
    "chatId": "5493300000001",
    "sessionCreationTime": "2026-05-02T11:00:00Z",
    "queue": "Ventas",
    "agentName": "Agente ETL",
    "agentId": "AGE01",
    "typification": "Consulta general",
    "closedTime": "2026-05-02T12:00:00Z",
    "fromOpAssignedToOpFirstResponse": 240,
    "openSessions": 0,
    "closedSessions": 1,
}]

MEDIA_URL = "https://storage.googleapis.com/storage.botmaker.com/tEtl/foto.png"
AUDIO_URL = "https://storage.botmaker.com/tEtl/audio.wav"
MISSING_URL = "https://storage.botmaker.com/tEtl/borrado.png"
TEMP_URL = "https://signed.example.com/tEtl/audio.wav?sig=abc"

MESSAGES = [
    {
        "id": "etl-m1",
        "creationTime": "2026-05-02T10:00:10Z",
        "from": "user",
        "sessionId": "etl-s-open",
        "sessionCreationTime": "2026-05-02T10:00:00Z",
        "chat": {"chatId": "5493300000001", "channelId": "whatsapp",
                 "contactId": "5493300000001"},
        "content": {"type": "text", "text": "Hola, tuve un siniestro"},
    },
    {
        "id": "etl-m2",
        "creationTime": "2026-05-02T10:00:20Z",
        "from": "bot",
        "sessionId": "etl-s-open",
        "sessionCreationTime": "2026-05-02T10:00:00Z",
        "chat": {"chatId": "5493300000001", "channelId": "whatsapp",
                 "contactId": "5493300000001"},
        "content": {
            "type": "text",
            "text": "Selecciona una opción",
            "buttons": ["Denunciar siniestro", "Hablar con un agente"],
            "whatsAppTemplateName": "bienvenida",
        },
    },
    {
        "id": "etl-m3",
        "creationTime": "2026-05-02T10:00:30Z",
        "from": "user",
        "sessionId": "etl-s-open",
        "sessionCreationTime": "2026-05-02T10:00:00Z",
        "chat": {"chatId": "5493300000001", "channelId": "whatsapp",
                 "contactId": "5493300000001"},
        "content": {
            "type": "image",
            "selectedButton": "Denunciar siniestro",
            "media": {"url": MEDIA_URL, "caption": "la foto del auto"},
        },
    },
    {
        "id": "etl-m4",
        "creationTime": "2026-05-02T10:00:40Z",
        "from": "user",
        "sessionId": "etl-s-open",
        "sessionCreationTime": "2026-05-02T10:00:00Z",
        "chat": {"chatId": "5493300000001", "channelId": "whatsapp",
                 "contactId": "5493300000001"},
        "content": {
            "type": "audio",
            "originalAudioUrl": AUDIO_URL,
            "location": {"latitude": "-34.6", "longitude": "-58.4",
                         "name": "Obelisco", "address": "Av. 9 de Julio"},
        },
        "encryptionParams": {"version": "1", "configId": "c1",
                             "timestamp": "1714600000", "encryptedKey": "k=="},
    },
    {
        "id": "etl-m5",
        "creationTime": "2026-05-02T10:00:50Z",
        "from": "user",
        "sessionId": "etl-s-open",
        "sessionCreationTime": "2026-05-02T10:00:00Z",
        "chat": {"chatId": "5493300000001", "channelId": "whatsapp",
                 "contactId": "5493300000001"},
        "content": {"type": "image", "media": {"url": MISSING_URL}},
    },
]

CHAT_DETAIL = {
    "chat": {
        "chatId": "5493300000001",
        "creationTime": "2026-05-01T00:00:00Z",
        "firstName": "Cliente",
        "lastName": "Etl",
        "country": "AR",
        "email": "cliente@etl.com",
        "variables": {"poliza": "POL-ETL-1"},
        "tags": ["siniestro"],
        "isTester": False,
        "isBotMuted": False,
        "isBanned": False,
    }
}


def build_standard_session() -> FakeBotmakerSession:
    """Sesión con el escenario completo: media pública OK, audio privado (403 →
    temp-link), archivo borrado (CDN 200 + JSON 'No file found'), chat detail."""
    s = FakeBotmakerSession()

    def paged(items):
        def handler(url, params, headers):
            return FakeResponse(200, json_data={"data": items, "nextPage": None})
        return handler

    s.route("GET", "https://api.botmaker.com/v2.0/dashboards/agent-performance",
            paged(AGENT_PERFORMANCE))

    def metrics(url, params, headers):
        items = AGENT_METRICS_OPEN if params.get("session-status") == "open" \
            else AGENT_METRICS_CLOSED
        return FakeResponse(200, json_data={"data": items})

    s.route("GET", "https://api.botmaker.com/v2.0/dashboards/agent-metrics", metrics)
    s.route("GET", "https://api.botmaker.com/v2.0/messages", paged(MESSAGES))
    s.route("GET", "https://api.botmaker.com/v2.0/chats/5493300000001",
            lambda u, p, h: FakeResponse(200, json_data=CHAT_DETAIL))
    s.route("GET", "https://api.botmaker.com/v2.0/private-media/temp-access-link",
            lambda u, p, h: FakeResponse(200, json_data={"tempUrl": TEMP_URL}))

    # CDN
    s.route("GET", MEDIA_URL,
            lambda u, p, h: FakeResponse(200, content=PNG, headers={"Content-Type": "image/png"}))
    s.route("GET", AUDIO_URL, lambda u, p, h: FakeResponse(403))
    s.route("GET", TEMP_URL,
            lambda u, p, h: FakeResponse(200, content=WAV, headers={"Content-Type": "audio/wav"}))
    s.route("GET", MISSING_URL,
            lambda u, p, h: FakeResponse(
                200, json_data={"message": "No file found for the given URL"}))
    return s


def make_client(session: FakeBotmakerSession, on_rotated=None, **kw):
    from worker.etl.botmaker import BotmakerClient

    return BotmakerClient(
        client_id="cid", secret_id="sid",
        access_token="tok-1", refresh_token="ref-1",
        on_tokens_rotated=on_rotated or (lambda a, r: None),
        session=session,
        min_interval=0, jitter_max_ms=0, backoff_base=0.01, max_retries=3,
        **kw,
    )
