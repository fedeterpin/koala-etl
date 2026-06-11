"""Métricas con números calculados a mano (ver factories.py)."""


async def test_summary_general(client, a_admin_headers):
    r = await client.get("/api/v1/metrics/summary", headers=a_admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total_sessions"] == 4
    assert data["unique_clients"] == 2
    # promedio sin ceros ni NULL: (120s + 600s) / 2 = 360s = 6 min
    assert data["avg_first_response_min"] == 6.0
    assert data["sessions_no_agent"] == 1
    assert data["pct_sessions_no_agent"] == 25.0
    assert data["templates_sent"] == 1
    assert data["sessions_started_by_external"] == 1


async def test_summary_contexto_siniestros_por_cola(client, a_admin_headers):
    r = await client.get(
        "/api/v1/metrics/summary?context=siniestros", headers=a_admin_headers
    )
    data = r.json()
    # s2 (Beto) y s3 (sin agente) están en la cola Siniestros
    assert data["total_sessions"] == 2
    assert data["sessions_no_agent"] == 1
    assert data["avg_first_response_min"] == 10.0  # solo s2 (600s)


async def test_filtro_de_fechas(client, a_admin_headers):
    r = await client.get(
        "/api/v1/metrics/summary?from=2026-03-01T00:00:00Z&to=2026-03-31T23:59:59Z",
        headers=a_admin_headers,
    )
    data = r.json()
    assert data["total_sessions"] == 2  # s2 y s3


async def test_sessions_by_month(client, a_admin_headers):
    r = await client.get("/api/v1/metrics/sessions-by-month", headers=a_admin_headers)
    items = {i["period"]: i["sessions"] for i in r.json()["items"]}
    assert items == {"2026-02": 2, "2026-03": 2}


async def test_sessions_by_month_por_agente(client, a_admin_headers):
    r = await client.get(
        "/api/v1/metrics/sessions-by-month?by_agent=true", headers=a_admin_headers
    )
    rows = {(i["period"], i["agent_name"]): i["sessions"] for i in r.json()["items"]}
    assert rows[("2026-02", "Ana")] == 2
    assert rows[("2026-03", "Beto")] == 1
    assert rows[("2026-03", "(sin agente)")] == 1


async def test_sessions_by_agent(client, a_admin_headers):
    r = await client.get("/api/v1/metrics/sessions-by-agent", headers=a_admin_headers)
    rows = {i["agent_name"]: i for i in r.json()["items"]}
    assert rows["Ana"]["sessions"] == 2
    assert rows["Ana"]["clients"] == 2  # c1 (s1) y c2 (s4)
    assert rows["Beto"]["sessions"] == 1
    assert rows["(sin agente)"]["sessions"] == 1


async def test_first_response_by_agent_promedio_sin_ceros(client, a_admin_headers):
    r = await client.get(
        "/api/v1/metrics/first-response-by-agent", headers=a_admin_headers
    )
    rows = {i["agent_name"]: i["avg_minutes"] for i in r.json()["items"]}
    # Ana: s1=120s=2min; s4=0 EXCLUIDO → 2.0. Beto: 600s → 10.0
    assert float(rows["Ana"]) == 2.0
    assert float(rows["Beto"]) == 10.0


async def test_clients_by_month(client, a_admin_headers):
    r = await client.get("/api/v1/metrics/clients-by-month", headers=a_admin_headers)
    items = {i["period"]: i["clients"] for i in r.json()["items"]}
    assert items == {"2026-02": 2, "2026-03": 2}


async def test_templates_by_month(client, a_admin_headers):
    r = await client.get("/api/v1/metrics/templates-by-month", headers=a_admin_headers)
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["template"] == "recordatorio_pago"
    assert items[0]["sent"] == 1


async def test_button_segmentation(client, a_admin_headers):
    r = await client.get("/api/v1/metrics/button-segmentation", headers=a_admin_headers)
    items = r.json()["items"]
    assert items == [
        {"button": "Denunciar siniestro", "times_selected": 1, "sessions": 1}
    ]


async def test_contact_rankings(client, a_admin_headers):
    r = await client.get(
        "/api/v1/metrics/contact-rankings?kind=sessions", headers=a_admin_headers
    )
    items = r.json()["items"]
    assert items[0]["value"] == 2  # ambos chats tienen 2 sesiones
    assert {i["chat_id"] for i in items} == {"5491100000001", "5491100000002"}

    r = await client.get(
        "/api/v1/metrics/contact-rankings?kind=messages", headers=a_admin_headers
    )
    rows = {i["chat_id"]: i["value"] for i in r.json()["items"]}
    assert rows == {"5491100000001": 4, "5491100000002": 2}

    r = await client.get(
        "/api/v1/metrics/contact-rankings?kind=external", headers=a_admin_headers
    )
    rows = {i["chat_id"]: i["value"] for i in r.json()["items"]}
    assert rows == {"5491100000001": 1}  # s1 empieza con user; s3 empieza con bot
