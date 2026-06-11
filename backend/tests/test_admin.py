from sqlalchemy import text


async def test_superadmin_crea_tenant_y_settings(client, sa_headers):
    r = await client.post("/api/v1/tenants", headers=sa_headers, json={
        "tenant_id": "tNuevo", "tenant_name": "Tenant Nuevo",
    })
    assert r.status_code == 201
    r = await client.get("/api/v1/tenants/tNuevo/settings", headers=sa_headers)
    assert r.status_code == 200
    assert r.json()["has_botmaker_credentials"] is False


async def test_tenant_admin_no_crea_tenants(client, a_admin_headers):
    r = await client.post("/api/v1/tenants", headers=a_admin_headers, json={
        "tenant_id": "tHack", "tenant_name": "Hack",
    })
    assert r.status_code == 403


async def test_credenciales_botmaker_write_only_y_cifradas(client, sa_headers, database):
    r = await client.put("/api/v1/tenants/tA/settings", headers=sa_headers, json={
        "botmaker_client_id": "cid-123",
        "botmaker_secret_id": "sid-456",
        "botmaker_token": "token-secreto-plano",
        "botmaker_refresh_token": "refresh-secreto-plano",
        "is_etl_enabled": True,
    })
    assert r.status_code == 200
    out = r.json()
    assert out["has_botmaker_credentials"] is True
    # nunca se devuelven los tokens
    assert "token-secreto-plano" not in r.text
    assert "botmaker_token" not in out or out.get("botmaker_token") is None

    # cifradas at-rest
    with database.connect() as conn:
        row = conn.execute(text(
            "SELECT botmaker_token_enc, botmaker_refresh_token_enc "
            "FROM tenant_settings WHERE tenant_id = 'tA'"
        )).one()
    assert row.botmaker_token_enc != "token-secreto-plano"
    assert "token-secreto-plano" not in row.botmaker_token_enc

    from app.core.crypto import decrypt_secret

    assert decrypt_secret(row.botmaker_token_enc) == "token-secreto-plano"
    assert decrypt_secret(row.botmaker_refresh_token_enc) == "refresh-secreto-plano"


async def test_tenant_admin_crea_y_desactiva_viewer(client, a_admin_headers):
    r = await client.post("/api/v1/users", headers=a_admin_headers, json={
        "email": "nuevo-viewer@test.com", "password": "Password1!",
        "full_name": "Nuevo Viewer", "role": "viewer",
    })
    assert r.status_code == 201
    uid = r.json()["id"]
    assert r.json()["tenant_id"] == "tA"

    # duplicado
    r = await client.post("/api/v1/users", headers=a_admin_headers, json={
        "email": "nuevo-viewer@test.com", "password": "Password1!",
        "full_name": "Duplicado", "role": "viewer",
    })
    assert r.status_code == 409

    # baja lógica
    r = await client.delete(f"/api/v1/users/{uid}", headers=a_admin_headers)
    assert r.status_code == 204
    r = await client.post("/api/v1/auth/login", json={
        "email": "nuevo-viewer@test.com", "password": "Password1!",
    })
    assert r.status_code == 401


async def test_tenant_admin_no_crea_superadmin(client, a_admin_headers):
    r = await client.post("/api/v1/users", headers=a_admin_headers, json={
        "email": "evil@test.com", "password": "Password1!",
        "full_name": "Evil", "role": "superadmin",
    })
    assert r.status_code == 403


async def test_tenant_admin_no_crea_usuario_en_otro_tenant(client, a_admin_headers):
    r = await client.post("/api/v1/users", headers=a_admin_headers, json={
        "email": "intruso@test.com", "password": "Password1!",
        "full_name": "Intruso", "role": "viewer", "tenant_id": "tB",
    })
    assert r.status_code == 403
