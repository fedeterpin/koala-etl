"""Corrida completa del ETL multi-tenant contra el Botmaker falso + Postgres + S3 (moto)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from tests.fake_botmaker import build_standard_session, make_client

NOW = datetime(2026, 5, 10, tzinfo=UTC)


@pytest.fixture(scope="module")
def etl_tenant(database):
    """Tenant dedicado para el ETL (no contamina los números de tests de métricas)."""
    with database.connect() as conn:
        conn.execute(text(
            "INSERT INTO tenants (tenant_id, tenant_name) VALUES ('tEtl', 'Tenant ETL') "
            "ON CONFLICT DO NOTHING"
        ))
        conn.execute(text(
            "INSERT INTO tenant_settings (tenant_id, etl_initial_ts, etl_window_days, is_etl_enabled) "
            "VALUES ('tEtl', '2026-05-01T00:00:00Z', 30, true) ON CONFLICT DO NOTHING"
        ))
        conn.commit()
    return "tEtl"


@pytest.fixture(scope="module")
def session_factory(database):
    return sessionmaker(database, expire_on_commit=False)


@pytest.fixture(scope="module")
def etl_run_id(etl_tenant, session_factory, s3_mock):
    """Corre el ETL completo una vez para todo el módulo."""
    from worker.etl.runner import run_tenant_etl

    client = make_client(build_standard_session())
    return run_tenant_etl(
        session_factory, s3_mock, get_settings().s3_bucket, etl_tenant,
        client=client, now=NOW,
    )


def test_corrida_registrada_en_etl_runs(etl_run_id, session_factory):
    from app.models import EtlRun

    with session_factory() as db:
        run = db.get(EtlRun, etl_run_id)
    assert run.status == "ok"
    assert run.finished_at is not None
    assert run.stats["agent_performance"]["rows"] == 1
    assert run.stats["agent_metrics"]["rows"] == 2  # open + closed (§11.5)
    assert run.stats["messages"]["rows"] == 5
    assert run.stats["messages"]["files_ok"] == 2   # media pública + audio vía temp-link
    assert run.stats["messages"]["files_failed"] == 1  # CDN 'No file found'
    assert run.stats["chat_details"]["rows"] == 1


def test_datos_cargados(etl_run_id, session_factory):
    from app.models import (
        Agent,
        AgentMetric,
        ChatDetail,
        ChatTag,
        ChatVariable,
        Message,
        MessageButton,
        MessageLocation,
    )

    with session_factory() as db:
        agents = list(db.scalars(select(Agent).where(Agent.tenant_id == "tEtl")))
        assert [a.agent_email for a in agents] == ["etl-agent@tetl.com"]

        metrics = {m.session_id: m for m in db.scalars(
            select(AgentMetric).where(AgentMetric.tenant_id == "tEtl")
        )}
        assert set(metrics) == {"etl-s-open", "etl-s-closed"}
        assert metrics["etl-s-closed"].from_op_assigned_to_op_first_response == 240
        assert metrics["etl-s-open"].agent_id is None

        msgs = list(db.scalars(select(Message).where(Message.tenant_id == "tEtl")))
        assert len(msgs) == 5
        templates = [m.whatsapp_template_name for m in msgs if m.whatsapp_template_name]
        assert templates == ["bienvenida"]

        buttons = list(db.scalars(
            select(MessageButton.button).where(
                (MessageButton.tenant_id == "tEtl") & (MessageButton.message_id == "etl-m2")
            )
        ))
        assert sorted(buttons) == ["Denunciar siniestro", "Hablar con un agente"]

        loc = db.get(MessageLocation, ("tEtl", "etl-m4"))
        assert loc is not None and loc.name == "Obelisco"

        detail = db.get(ChatDetail, ("tEtl", "5493300000001"))
        assert detail.first_name == "Cliente"
        assert db.get(ChatVariable, ("tEtl", "5493300000001", "poliza")).var_value == "POL-ETL-1"
        assert db.get(ChatTag, ("tEtl", "5493300000001", "siniestro")) is not None


def test_archivos_en_s3_y_estados(etl_run_id, session_factory, s3_mock):
    from app.models import MessageFile

    with session_factory() as db:
        files = {(f.message_id, f.file_type): f for f in db.scalars(
            select(MessageFile).where(MessageFile.tenant_id == "tEtl")
        )}

    media = files[("etl-m3", "media")]
    assert media.status == "ok"
    assert media.s3_key == "tenants/tEtl/files/etl-m3/media/foto.png"
    assert media.content_type == "image/png"
    obj = s3_mock.get_object(Bucket=get_settings().s3_bucket, Key=media.s3_key)
    assert obj["Body"].read().startswith(b"\x89PNG")

    audio = files[("etl-m4", "audio")]  # privado: 403 → temp-link → ok
    assert audio.status == "ok"
    assert audio.s3_key.endswith("audio.wav")

    missing = files[("etl-m5", "media")]  # CDN 200 + JSON "No file found" (§11.3)
    assert missing.status == "not_found"
    assert missing.s3_key is None


def test_ventana_actualizada_en_etl_control(etl_run_id, session_factory):
    from app.models import EtlControl

    with session_factory() as db:
        rows = {c.endpoint: c.last_ts for c in db.scalars(
            select(EtlControl).where(EtlControl.tenant_id == "tEtl")
        )}
    assert set(rows) == {"agent-performance", "agent-metrics", "messages"}
    # to = min(initial + 30 días, now=10-may) → now
    assert all(ts == NOW for ts in rows.values())


def test_reejecutar_es_idempotente(etl_run_id, session_factory, s3_mock):
    from app.models import Message, MessageButton
    from worker.etl.runner import run_tenant_etl

    client = make_client(build_standard_session())
    run2 = run_tenant_etl(
        session_factory, s3_mock, get_settings().s3_bucket, "tEtl",
        client=client, now=NOW,
    )
    with session_factory() as db:
        n_msgs = len(list(db.scalars(select(Message).where(Message.tenant_id == "tEtl"))))
        n_btns = len(list(db.scalars(
            select(MessageButton).where(MessageButton.tenant_id == "tEtl")
        )))
    assert n_msgs == 5
    assert n_btns == 2
    assert run2 != etl_run_id


def test_etapa_que_falla_no_frena_las_demas(session_factory, s3_mock, database):
    """Aislamiento de etapas: si agent-performance falla, messages corre igual."""
    from app.models import EtlRun, EtlStageError
    from tests.fake_botmaker import FakeBotmakerSession, FakeResponse, build_standard_session

    with database.connect() as conn:
        conn.execute(text(
            "INSERT INTO tenants (tenant_id, tenant_name) VALUES ('tEtl2', 'Tenant ETL 2') "
            "ON CONFLICT DO NOTHING"
        ))
        conn.execute(text(
            "INSERT INTO tenant_settings (tenant_id, etl_initial_ts, etl_window_days, is_etl_enabled) "
            "VALUES ('tEtl2', '2026-05-01T00:00:00Z', 30, true) ON CONFLICT DO NOTHING"
        ))
        conn.commit()

    base = build_standard_session()
    broken = FakeBotmakerSession()
    # agent-performance devuelve 400 SIEMPRE; el resto delega en el escenario estándar
    broken.route("GET", "https://api.botmaker.com/v2.0/dashboards/agent-performance",
                 lambda u, p, h: FakeResponse(400))
    for m, prefix, fn in base.routes:
        if "agent-performance" not in prefix:
            broken.route(m, prefix, fn)
    # los datos del escenario apuntan a chatId de tEtl; reusarlos para tEtl2 es válido

    from worker.etl.runner import run_tenant_etl

    run_id = run_tenant_etl(
        session_factory, s3_mock, get_settings().s3_bucket, "tEtl2",
        client=make_client(broken), now=NOW,
    )
    with session_factory() as db:
        run = db.get(EtlRun, run_id)
        errors = list(db.scalars(select(EtlStageError).where(EtlStageError.run_id == run_id)))
    assert run.status == "partial"
    assert run.stats["messages"]["rows"] == 5  # las demás etapas corrieron
    assert [e.stage for e in errors] == ["agent_performance"]
    assert "agent_performance" in run.error_summary
