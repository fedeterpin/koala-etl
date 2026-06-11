"""Tests del cliente Botmaker: refresh con rotación, 429, temp-link, paginación."""

import pytest
import requests

from tests.fake_botmaker import FakeBotmakerSession, FakeResponse, make_client


def test_401_dispara_refresh_y_persiste_rotacion():
    s = FakeBotmakerSession()
    state = {"token": "tok-1", "rotated": None}

    def api(url, params, headers):
        if headers.get("access-token") == "tok-2":
            return FakeResponse(200, json_data={"data": [{"x": 1}]})
        return FakeResponse(401)

    def refresh(url, params, headers):
        assert headers["clientId"] == "cid"
        assert headers["refreshToken"] == "ref-1"
        return FakeResponse(200, json_data={"accessToken": "tok-2", "refreshToken": "ref-2"})

    s.route("GET", "https://api.botmaker.com/v2.0/messages", api)
    s.route("POST", "https://go.botmaker.com/api/v1.0/auth/credentials", refresh)

    client = make_client(s, on_rotated=lambda a, r: state.update(rotated=(a, r)))
    items = client.fetch_all("https://api.botmaker.com/v2.0/messages")
    assert items == [{"x": 1}]
    # el refresh token ROTA y debe persistirse inmediatamente (§11.1)
    assert state["rotated"] == ("tok-2", "ref-2")
    assert client.refresh_token == "ref-2"


def test_refresh_204_no_cambia_tokens():
    s = FakeBotmakerSession()
    s.route("POST", "https://go.botmaker.com/api/v1.0/auth/credentials",
            lambda u, p, h: FakeResponse(204))
    client = make_client(s)
    client.refresh_credentials()
    assert client.access_token == "tok-1"
    assert client.refresh_token == "ref-1"


def test_429_reintenta_respetando_retry_after():
    s = FakeBotmakerSession()
    state = {"calls": 0}

    def api(url, params, headers):
        state["calls"] += 1
        if state["calls"] < 3:
            return FakeResponse(429, headers={"Retry-After": "0"})
        return FakeResponse(200, json_data={"data": [{"ok": True}]})

    s.route("GET", "https://api.botmaker.com/v2.0/messages", api)
    client = make_client(s)
    items = client.fetch_all("https://api.botmaker.com/v2.0/messages")
    assert items == [{"ok": True}]
    assert state["calls"] == 3


def test_4xx_no_reintentable_levanta():
    s = FakeBotmakerSession()
    s.route("GET", "https://api.botmaker.com/v2.0/messages",
            lambda u, p, h: FakeResponse(400))
    client = make_client(s)
    with pytest.raises(requests.HTTPError):
        client.request("GET", "https://api.botmaker.com/v2.0/messages")


def test_paginacion_next_page():
    s = FakeBotmakerSession()

    def page1(url, params, headers):
        return FakeResponse(200, json_data={
            "data": [{"i": 1}],
            "nextPage": "https://api.botmaker.com/v2.0/messages?page=2",
        })

    def page2(url, params, headers):
        if "page=2" in url:
            return FakeResponse(200, json_data={"data": [{"i": 2}]})
        return None

    s.route("GET", "https://api.botmaker.com/v2.0/messages?page=2", page2)
    s.route("GET", "https://api.botmaker.com/v2.0/messages", page1)
    client = make_client(s)
    items = client.fetch_all("https://api.botmaker.com/v2.0/messages")
    assert items == [{"i": 1}, {"i": 2}]


def test_temp_link_usa_url_alternativa():
    """Si el temp-link falla con la URL de GCS, prueba storage.botmaker.com (§11.4)."""
    s = FakeBotmakerSession()
    gcs = "https://storage.googleapis.com/storage.botmaker.com/t/x.png"

    def temp(url, params, headers):
        if params["file-url"] == gcs:
            return FakeResponse(404)
        if params["file-url"] == "https://storage.botmaker.com/t/x.png":
            return FakeResponse(200, json_data={"tempUrl": "https://ok.example.com/x"})
        return FakeResponse(500)

    s.route("GET", "https://api.botmaker.com/v2.0/private-media/temp-access-link", temp)
    client = make_client(s)
    assert client.get_temp_link(gcs) == "https://ok.example.com/x"
