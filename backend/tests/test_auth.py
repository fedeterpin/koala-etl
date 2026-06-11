from tests.conftest import login


async def test_login_ok(client):
    r = await client.post(
        "/api/v1/auth/login", json={"email": "a-admin@test.com", "password": "Test1234!"}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["access_token"] and data["refresh_token"]
    assert data["user"]["role"] == "tenant_admin"
    assert data["user"]["tenant_id"] == "tA"


async def test_login_password_incorrecta(client):
    r = await client.post(
        "/api/v1/auth/login", json={"email": "a-admin@test.com", "password": "incorrecta1"}
    )
    assert r.status_code == 401


async def test_login_usuario_inactivo(client):
    r = await client.post(
        "/api/v1/auth/login", json={"email": "a-inactive@test.com", "password": "Test1234!"}
    )
    assert r.status_code == 401


async def test_refresh_devuelve_par_nuevo(client):
    r = await client.post(
        "/api/v1/auth/login", json={"email": "a-admin@test.com", "password": "Test1234!"}
    )
    refresh = r.json()["refresh_token"]
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 200
    assert r2.json()["access_token"]


async def test_refresh_no_acepta_access_token(client):
    r = await client.post(
        "/api/v1/auth/login", json={"email": "a-admin@test.com", "password": "Test1234!"}
    )
    access = r.json()["access_token"]
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert r2.status_code == 401


async def test_me_incluye_tenant(client, a_admin_headers):
    r = await client.get("/api/v1/auth/me", headers=a_admin_headers)
    assert r.status_code == 200
    assert r.json()["tenant_name"] == "Tenant A"


async def test_endpoint_sin_token_da_401(client):
    r = await client.get("/api/v1/chats")
    assert r.status_code == 401


async def test_rate_limit_de_login(client):
    # email único para no contaminar el limiter de otros tests
    for _ in range(5):
        r = await client.post(
            "/api/v1/auth/login",
            json={"email": "fuerza-bruta@test.com", "password": "incorrecta1"},
        )
        assert r.status_code == 401
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "fuerza-bruta@test.com", "password": "incorrecta1"},
    )
    assert r.status_code == 429


async def test_login_audita(client, database):
    from sqlalchemy import text

    await login(client, "a-viewer@test.com")
    with database.connect() as conn:
        n = conn.execute(text(
            "SELECT count(*) FROM audit_log WHERE action = 'login_ok'"
        )).scalar()
    assert n >= 1
