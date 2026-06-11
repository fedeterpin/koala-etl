"""Tests de fuga cross-tenant (§8.1): el usuario A no puede ver chats, archivos
ni métricas de B, incluso adivinando ids."""

B_CHAT = "5492200000001"
B_MESSAGE = "mB1"


async def test_lista_de_chats_solo_del_propio_tenant(client, a_admin_headers):
    r = await client.get("/api/v1/chats", headers=a_admin_headers)
    assert r.status_code == 200
    ids = [c["chat_id"] for c in r.json()["items"]]
    assert ids and all(i.startswith("54911") for i in ids)
    assert B_CHAT not in ids


async def test_chat_de_otro_tenant_da_404(client, a_admin_headers):
    r = await client.get(f"/api/v1/chats/{B_CHAT}", headers=a_admin_headers)
    assert r.status_code == 404
    r = await client.get(f"/api/v1/chats/{B_CHAT}/messages", headers=a_admin_headers)
    assert r.status_code == 404


async def test_archivo_de_otro_tenant_da_404(client, a_admin_headers):
    r = await client.get(f"/api/v1/files/{B_MESSAGE}/media/url", headers=a_admin_headers)
    assert r.status_code == 404


async def test_query_param_tenant_id_ajeno_da_403(client, a_admin_headers):
    for path in ("/api/v1/chats", "/api/v1/metrics/summary", "/api/v1/files/failed"):
        r = await client.get(f"{path}?tenant_id=tB", headers=a_admin_headers)
        assert r.status_code == 403, f"{path}: {r.status_code}"


async def test_metricas_no_mezclan_tenants(client, a_admin_headers, b_admin_headers):
    a = (await client.get("/api/v1/metrics/summary", headers=a_admin_headers)).json()
    b = (await client.get("/api/v1/metrics/summary?tenant_id=tB", headers=b_admin_headers)).json()
    assert a["total_sessions"] == 4
    assert b["total_sessions"] == 1


async def test_superadmin_requiere_tenant_id_explicito(client, sa_headers):
    r = await client.get("/api/v1/chats", headers=sa_headers)
    assert r.status_code == 400
    r = await client.get("/api/v1/chats?tenant_id=tB", headers=sa_headers)
    assert r.status_code == 200
    assert [c["chat_id"] for c in r.json()["items"]] == [B_CHAT]


async def test_viewer_no_administra_usuarios(client, a_viewer_headers):
    r = await client.get("/api/v1/users", headers=a_viewer_headers)
    assert r.status_code == 403
    r = await client.post("/api/v1/users", headers=a_viewer_headers, json={
        "email": "x@test.com", "password": "Password1!", "full_name": "X", "role": "viewer",
    })
    assert r.status_code == 403


async def test_admin_no_ve_usuarios_de_otro_tenant(client, a_admin_headers, b_admin_headers):
    users_a = (await client.get("/api/v1/users", headers=a_admin_headers)).json()
    emails_a = {u["email"] for u in users_a}
    assert "b-admin@test.com" not in emails_a

    # A no puede modificar un usuario de B (ni saber que existe)
    users_b = (await client.get("/api/v1/users", headers=b_admin_headers)).json()
    b_id = next(u["id"] for u in users_b if u["email"] == "b-admin@test.com")
    r = await client.patch(
        f"/api/v1/users/{b_id}", headers=a_admin_headers, json={"full_name": "hackeado"}
    )
    assert r.status_code == 404


async def test_retry_y_backups_scoped(client, a_admin_headers):
    r = await client.get("/api/v1/files/retry-jobs?tenant_id=tB", headers=a_admin_headers)
    assert r.status_code == 403
    r = await client.get("/api/v1/backups?tenant_id=tB", headers=a_admin_headers)
    assert r.status_code == 403


async def test_etl_runs_scoped(client, a_admin_headers):
    r = await client.get("/api/v1/etl/runs?tenant_id=tB", headers=a_admin_headers)
    assert r.status_code == 403
    r = await client.get("/api/v1/etl/runs", headers=a_admin_headers)
    assert r.status_code == 200
