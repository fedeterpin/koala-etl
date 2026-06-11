"""Dataset de tests calculado a mano (para asserts exactos en métricas).

Tenant A (tA) — Siniestros configurado por cola:
  Sesiones (agent_metrics):
    s1: chat c1, Ana,  Ventas,     2026-02-10, first_resp=120s, cerrada
    s2: chat c1, Beto, Siniestros, 2026-03-05, first_resp=600s, cerrada
    s3: chat c2, sin agente, Siniestros, 2026-03-06, first_resp NULL, abierta
    s4: chat c2, Ana,  Ventas,     2026-02-20, first_resp=0 (excluido del promedio)
  → summary general: total=4, unique=2, avg_first_resp=6.0 min, sin agente=1 (25%)
  → context siniestros (cola): s2 y s3 → total=2
  Mensajes:
    s1: m1 user / m2 bot (botones) / m3 user selected='Denunciar siniestro' / m4 bot template
    s3: m5 bot / m6 user
  → iniciadas por externo=1 (s1) ; templates=1 (m4)
  Archivos: m3 media ok (en S3), m6 media forbidden, m1 audio error

Tenant B (tB): 1 chat, 1 sesión, 1 mensaje, 1 archivo ok.
"""

from datetime import UTC, datetime

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    Agent,
    AgentMetric,
    Chat,
    ChatDetail,
    ChatTag,
    ChatVariable,
    Message,
    MessageButton,
    MessageContent,
    MessageFile,
    Queue,
    Tenant,
    TenantSettings,
    User,
)

PASSWORD = "Test1234!"


def dt(year, month, day, hour=12, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def seed_test_data(engine, s3_client, bucket: str) -> None:
    with Session(engine) as db:
        # ——— Tenants y settings ———
        db.execute(insert(Tenant), [
            {"tenant_id": "tA", "tenant_name": "Tenant A", "created_at": dt(2026, 1, 1)},
            {"tenant_id": "tB", "tenant_name": "Tenant B", "created_at": dt(2026, 1, 1)},
        ])
        db.execute(insert(TenantSettings), [
            {"tenant_id": "tA", "siniestros_queue": "Siniestros", "siniestros_button": None,
             "is_etl_enabled": False},
            {"tenant_id": "tB", "siniestros_queue": "Siniestros", "is_etl_enabled": False},
        ])

        # ——— Usuarios ———
        pw = hash_password(PASSWORD)
        db.execute(insert(User), [
            {"tenant_id": None, "email": "sa@test.com", "password_hash": pw,
             "full_name": "Super Admin", "role": "superadmin", "is_active": True},
            {"tenant_id": "tA", "email": "a-admin@test.com", "password_hash": pw,
             "full_name": "Admin A", "role": "tenant_admin", "is_active": True},
            {"tenant_id": "tA", "email": "a-viewer@test.com", "password_hash": pw,
             "full_name": "Viewer A", "role": "viewer", "is_active": True},
            {"tenant_id": "tB", "email": "b-admin@test.com", "password_hash": pw,
             "full_name": "Admin B", "role": "tenant_admin", "is_active": True},
            {"tenant_id": "tA", "email": "a-inactive@test.com", "password_hash": pw,
             "full_name": "Inactivo A", "role": "viewer", "is_active": False},
        ])

        # ——— Tenant A ———
        db.execute(insert(Queue), [
            {"tenant_id": "tA", "queue": "Ventas"},
            {"tenant_id": "tA", "queue": "Siniestros"},
            {"tenant_id": "tB", "queue": "Siniestros"},
        ])
        db.execute(insert(Agent), [
            {"tenant_id": "tA", "agent_email": "ana@ta.com", "agent_name": "Ana", "role": "agent"},
            {"tenant_id": "tA", "agent_email": "beto@ta.com", "agent_name": "Beto", "role": "agent"},
        ])
        db.execute(insert(Chat), [
            {"tenant_id": "tA", "chat_id": "5491100000001", "channel_id": "whatsapp",
             "contact_id": "5491100000001"},
            {"tenant_id": "tA", "chat_id": "5491100000002", "channel_id": "whatsapp",
             "contact_id": "5491100000002"},
            {"tenant_id": "tB", "chat_id": "5492200000001", "channel_id": "whatsapp",
             "contact_id": "5492200000001"},
        ])
        db.execute(insert(ChatDetail), [
            {"tenant_id": "tA", "chat_id": "5491100000001", "first_name": "Carla",
             "last_name": "Pérez", "creation_time": dt(2026, 2, 1), "country": "AR"},
            {"tenant_id": "tA", "chat_id": "5491100000002", "first_name": "Diego",
             "last_name": "Suárez", "creation_time": dt(2026, 3, 1), "country": "AR"},
            {"tenant_id": "tB", "chat_id": "5492200000001", "first_name": "Bruno",
             "last_name": "Bravo", "creation_time": dt(2026, 2, 1), "country": "AR"},
        ])
        db.execute(insert(ChatVariable), [
            {"tenant_id": "tA", "chat_id": "5491100000001", "var_key": "poliza", "var_value": "POL-1"},
        ])
        db.execute(insert(ChatTag), [
            {"tenant_id": "tA", "chat_id": "5491100000001", "tag": "vip"},
        ])

        db.execute(insert(AgentMetric), [
            {"tenant_id": "tA", "session_id": "s1", "chat_id": "5491100000001",
             "session_creation_time": dt(2026, 2, 10), "queue": "Ventas",
             "agent_name": "Ana", "agent_id": "AG001",
             "from_op_assigned_to_op_first_response": 120,
             "closed_time": dt(2026, 2, 10, 14), "closed_sessions": 1, "open_sessions": 0},
            {"tenant_id": "tA", "session_id": "s2", "chat_id": "5491100000001",
             "session_creation_time": dt(2026, 3, 5), "queue": "Siniestros",
             "agent_name": "Beto", "agent_id": "AG002",
             "from_op_assigned_to_op_first_response": 600,
             "closed_time": dt(2026, 3, 5, 15), "closed_sessions": 1, "open_sessions": 0},
            {"tenant_id": "tA", "session_id": "s3", "chat_id": "5491100000002",
             "session_creation_time": dt(2026, 3, 6), "queue": "Siniestros",
             "agent_name": None, "agent_id": None,
             "from_op_assigned_to_op_first_response": None,
             "closed_time": None, "closed_sessions": 0, "open_sessions": 1},
            {"tenant_id": "tA", "session_id": "s4", "chat_id": "5491100000002",
             "session_creation_time": dt(2026, 2, 20), "queue": "Ventas",
             "agent_name": "Ana", "agent_id": "AG001",
             "from_op_assigned_to_op_first_response": 0,
             "closed_time": dt(2026, 2, 20, 13), "closed_sessions": 1, "open_sessions": 0},
            {"tenant_id": "tB", "session_id": "sB1", "chat_id": "5492200000001",
             "session_creation_time": dt(2026, 2, 15), "queue": "Siniestros",
             "agent_name": "Berta", "agent_id": "AGB01",
             "from_op_assigned_to_op_first_response": 300,
             "closed_time": dt(2026, 2, 15, 13), "closed_sessions": 1, "open_sessions": 0},
        ])

        msgs_a = [
            ("mA1", dt(2026, 2, 10, 12, 0), "user", "s1", dt(2026, 2, 10), "5491100000001", None),
            ("mA2", dt(2026, 2, 10, 12, 1), "bot", "s1", dt(2026, 2, 10), "5491100000001", None),
            ("mA3", dt(2026, 2, 10, 12, 2), "user", "s1", dt(2026, 2, 10), "5491100000001", None),
            ("mA4", dt(2026, 2, 10, 12, 3), "bot", "s1", dt(2026, 2, 10), "5491100000001",
             "recordatorio_pago"),
            ("mA5", dt(2026, 3, 6, 10, 0), "bot", "s3", dt(2026, 3, 6), "5491100000002", None),
            ("mA6", dt(2026, 3, 6, 10, 1), "user", "s3", dt(2026, 3, 6), "5491100000002", None),
        ]
        db.execute(insert(Message), [
            {"tenant_id": "tA", "id": mid, "creation_time": ts, "message_from": frm,
             "session_id": sid, "session_creation_time": sts, "chat_id": cid,
             "queue_id": None, "whatsapp_template_name": tpl}
            for mid, ts, frm, sid, sts, cid, tpl in msgs_a
        ])
        db.execute(insert(Message), [{
            "tenant_id": "tB", "id": "mB1", "creation_time": dt(2026, 2, 15, 12),
            "message_from": "user", "session_id": "sB1",
            "session_creation_time": dt(2026, 2, 15), "chat_id": "5492200000001",
            "queue_id": None, "whatsapp_template_name": None,
        }])

        db.execute(insert(MessageContent), [
            {"tenant_id": "tA", "message_id": "mA1", "content_type": "text",
             "text": "Hola, tuve un choque"},
            {"tenant_id": "tA", "message_id": "mA2", "content_type": "text",
             "text": "Selecciona una opción"},
            {"tenant_id": "tA", "message_id": "mA3", "content_type": "image",
             "text": "Denunciar siniestro", "selected_button": "Denunciar siniestro"},
            {"tenant_id": "tA", "message_id": "mA4", "content_type": "text",
             "text": "Recordatorio de pago"},
            {"tenant_id": "tA", "message_id": "mA5", "content_type": "text", "text": "Hola!"},
            {"tenant_id": "tA", "message_id": "mA6", "content_type": "image", "text": "foto"},
            {"tenant_id": "tB", "message_id": "mB1", "content_type": "text", "text": "Hola B"},
        ])
        db.execute(insert(MessageButton), [
            {"tenant_id": "tA", "message_id": "mA2", "button": "Denunciar siniestro"},
            {"tenant_id": "tA", "message_id": "mA2", "button": "Cotizar seguro"},
        ])

        ok_key_a = "tenants/tA/files/mA3/media/mA3.png"
        ok_key_b = "tenants/tB/files/mB1/media/mB1.png"
        png = b"\x89PNG\r\n\x1a\n-test-bytes"
        s3_client.put_object(Bucket=bucket, Key=ok_key_a, Body=png, ContentType="image/png")
        s3_client.put_object(Bucket=bucket, Key=ok_key_b, Body=png, ContentType="image/png")

        db.execute(insert(MessageFile), [
            {"tenant_id": "tA", "message_id": "mA3", "file_type": "media",
             "original_url": "https://storage.botmaker.com/tA/mA3.png", "s3_key": ok_key_a,
             "downloaded_at": dt(2026, 2, 10, 12, 2), "status": "ok",
             "size_bytes": len(png), "content_type": "image/png"},
            {"tenant_id": "tA", "message_id": "mA6", "file_type": "media",
             "original_url": "https://storage.botmaker.com/tA/mA6.png", "s3_key": None,
             "downloaded_at": dt(2026, 3, 6, 10, 1), "status": "forbidden"},
            {"tenant_id": "tA", "message_id": "mA1", "file_type": "audio",
             "original_url": "https://storage.botmaker.com/tA/mA1.ogg", "s3_key": None,
             "downloaded_at": dt(2026, 2, 10, 12, 0), "status": "error"},
            {"tenant_id": "tB", "message_id": "mB1", "file_type": "media",
             "original_url": "https://storage.botmaker.com/tB/mB1.png", "s3_key": ok_key_b,
             "downloaded_at": dt(2026, 2, 15, 12), "status": "ok",
             "size_bytes": len(png), "content_type": "image/png"},
        ])

        db.commit()
