from sqlalchemy import text


async def test_lista_chats_con_busqueda_y_preview(client, a_admin_headers):
    r = await client.get("/api/v1/chats?search=Carla", headers=a_admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["chat_id"] == "5491100000001"
    assert item["tags"] == ["vip"]
    assert item["last_message_preview"]


async def test_busqueda_por_telefono(client, a_admin_headers):
    r = await client.get("/api/v1/chats?search=5491100000002", headers=a_admin_headers)
    assert r.json()["total"] == 1


async def test_detalle_de_chat_con_variables_y_tags(client, a_admin_headers):
    r = await client.get("/api/v1/chats/5491100000001", headers=a_admin_headers)
    data = r.json()
    assert data["first_name"] == "Carla"
    assert data["variables"] == {"poliza": "POL-1"}
    assert data["tags"] == ["vip"]


async def test_timeline_de_mensajes(client, a_admin_headers):
    r = await client.get("/api/v1/chats/5491100000001/messages", headers=a_admin_headers)
    data = r.json()
    items = data["items"]
    assert [m["id"] for m in items] == ["mA1", "mA2", "mA3", "mA4"]  # ascendente
    by_id = {m["id"]: m for m in items}
    assert by_id["mA2"]["buttons"] == ["Cotizar seguro", "Denunciar siniestro"] or \
           set(by_id["mA2"]["buttons"]) == {"Denunciar siniestro", "Cotizar seguro"}
    assert by_id["mA3"]["selected_button"] == "Denunciar siniestro"
    assert by_id["mA4"]["whatsapp_template_name"] == "recordatorio_pago"
    files_a3 = by_id["mA3"]["files"]
    assert files_a3[0]["has_file"] is True
    files_a1 = by_id["mA1"]["files"]
    assert files_a1[0]["status"] == "error" and files_a1[0]["has_file"] is False


async def test_paginado_hacia_atras(client, a_admin_headers):
    r = await client.get(
        "/api/v1/chats/5491100000001/messages?limit=2", headers=a_admin_headers
    )
    data = r.json()
    assert [m["id"] for m in data["items"]] == ["mA3", "mA4"]
    assert data["has_more"] is True
    before = data["next_before"]
    r2 = await client.get(
        f"/api/v1/chats/5491100000001/messages?limit=2&before={before}",
        headers=a_admin_headers,
    )
    assert [m["id"] for m in r2.json()["items"]] == ["mA1", "mA2"]


async def test_url_prefirmada_para_archivo_ok(client, a_admin_headers):
    r = await client.get("/api/v1/files/mA3/media/url", headers=a_admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert "tenants/tA/files/mA3/media/mA3.png" in data["url"]
    assert data["expires_in"] <= 300  # TTL ≤ 5 min (§8.3)


async def test_url_de_archivo_fallido_da_409(client, a_admin_headers):
    r = await client.get("/api/v1/files/mA6/media/url", headers=a_admin_headers)
    assert r.status_code == 409


async def test_visualizaciones_se_auditan(client, a_admin_headers, database):
    await client.get("/api/v1/chats/5491100000001/messages", headers=a_admin_headers)
    await client.get("/api/v1/files/mA3/media/url", headers=a_admin_headers)
    with database.connect() as conn:
        chat_views = conn.execute(text(
            "SELECT count(*) FROM audit_log "
            "WHERE action = 'chat_viewed' AND tenant_id = 'tA'"
        )).scalar()
        file_urls = conn.execute(text(
            "SELECT count(*) FROM audit_log "
            "WHERE action = 'file_url_generated' AND entity_id = 'mA3/media'"
        )).scalar()
    assert chat_views >= 1
    assert file_urls >= 1


async def test_listado_de_fallidas_con_conteos(client, a_admin_headers):
    r = await client.get("/api/v1/files/failed", headers=a_admin_headers)
    data = r.json()
    assert data["total"] == 2  # mA6 forbidden + mA1 error
    assert data["counts_by_status"]["forbidden"] == 1
    assert data["counts_by_status"]["error"] == 1
    assert data["counts_by_status"]["ok"] == 1

    r = await client.get("/api/v1/files/failed?status=forbidden", headers=a_admin_headers)
    assert r.json()["total"] == 1


async def test_viewer_no_ve_fallidas(client, a_viewer_headers):
    r = await client.get("/api/v1/files/failed", headers=a_viewer_headers)
    assert r.status_code == 403


async def test_encolar_reintento(client, a_admin_headers):
    r = await client.post("/api/v1/files/retry", headers=a_admin_headers, json={
        "statuses": ["forbidden", "error"], "limit": 10,
    })
    assert r.status_code == 202
    job_id = r.json()["id"]
    assert r.json()["status"] == "pending"

    r = await client.get(f"/api/v1/files/retry-jobs/{job_id}", headers=a_admin_headers)
    assert r.status_code == 200


async def test_backup_crear_y_listar(client, a_admin_headers):
    r = await client.post("/api/v1/backups", headers=a_admin_headers, json={"type": "full"})
    assert r.status_code == 202
    backup_id = r.json()["id"]

    # segundo pedido mientras hay uno pendiente → 409
    r = await client.post("/api/v1/backups", headers=a_admin_headers, json={"type": "full"})
    assert r.status_code == 409

    r = await client.get("/api/v1/backups", headers=a_admin_headers)
    assert any(b["id"] == backup_id for b in r.json())

    # descarga de un backup no terminado → 409
    r = await client.get(f"/api/v1/backups/{backup_id}/download", headers=a_admin_headers)
    assert r.status_code == 409
