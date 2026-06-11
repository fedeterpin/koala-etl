"""Seed de datos de prueba multi-tenant (port de datos_prueba_volumen.sql del legacy).

Genera 2 tenants con ~300 chats cada uno para probar aislamiento, dashboards y visor.
Determinístico (random con semilla fija). Re-ejecutable: limpia primero los datos
de los tenants seed. Inserta por tabla en orden de dependencias (bulk insert).

Uso:
    python -m app.seed              # siembra (borra y recrea los tenants seed)
    python -m app.seed --if-empty   # solo siembra si no hay tenants (arranque docker)
"""

import argparse
import random
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, delete, insert, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import ROLE_SUPERADMIN, ROLE_TENANT_ADMIN, ROLE_VIEWER, hash_password
from app.models import (
    Agent,
    AgentMetric,
    AgentPerformance,
    AgentPerformanceQueue,
    AuditLog,
    BackupJob,
    Chat,
    ChatDetail,
    ChatTag,
    ChatVariable,
    EtlControl,
    EtlRun,
    Message,
    MessageButton,
    MessageContent,
    MessageFile,
    MessageMedia,
    Queue,
    RetryJob,
    Tenant,
    TenantSettings,
    User,
)

DATE_START = datetime(2026, 1, 1, tzinfo=UTC)
DATE_END = datetime(2026, 6, 1, tzinfo=UTC)
SPAN_MINUTES = int((DATE_END - DATE_START).total_seconds() // 60)

QUEUES = ["Siniestros", "Ventas", "Atencion_Cliente", "Postventa"]
TIPIFICACIONES = [
    "Denuncia siniestro", "Cotización", "Consulta general", "Siniestro granizo",
    "Cambio de plan", "Reclamo", "Pago de cuota", "Baja de servicio",
]
TAGS = ["siniestro", "urgente", "cotizacion", "consulta", "granizo", "mora", "vip", "reclamo"]
TIPOS_SEGURO = ["Automotor", "Hogar", "Vida", "Comercio"]
TEMPLATES = ["recordatorio_pago", "encuesta_satisfaccion", "aviso_siniestro", "bienvenida"]
BUTTONS_MENU = ["Denunciar siniestro", "Cotizar seguro", "Consultar póliza", "Hablar con un agente"]
NOMBRES = ["Juan", "María", "Pedro", "Sofía", "Jorge", "Valentina", "Luis", "Carla", "Hernán", "Rocío"]
APELLIDOS = ["Pérez", "García", "Rodríguez", "Suárez", "Acosta", "Molina", "Vega", "Castro", "Ibarra", "Funes"]

# Contenido binario mínimo válido para que el visor pueda mostrar media en dev
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcff9fa1060000060001ba34cf2c0000000049454e44ae426082"
)
TINY_WAV = (
    b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x40\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
)

TENANTS = [
    {
        "tenant_id": "GrupoRimoldi",
        "tenant_name": "Grupo Rimoldi Seguros",
        "phone_prefix": "5491145",
        "num_chats": 300,
        "seed": 42,
    },
    {
        "tenant_id": "AseguradoraDemo",
        "tenant_name": "Aseguradora Demo",
        "phone_prefix": "5491167",
        "num_chats": 300,
        "seed": 1337,
    },
]

USERS = [
    ("admin@koala.app", "Admin Koala", ROLE_SUPERADMIN, None, "Admin1234!"),
    ("admin@gruporimoldi.com", "Admin Rimoldi", ROLE_TENANT_ADMIN, "GrupoRimoldi", "Rimoldi1234!"),
    ("viewer@gruporimoldi.com", "Viewer Rimoldi", ROLE_VIEWER, "GrupoRimoldi", "Rimoldi1234!"),
    ("admin@demo.com", "Admin Demo", ROLE_TENANT_ADMIN, "AseguradoraDemo", "Demo1234!"),
    ("viewer@demo.com", "Viewer Demo", ROLE_VIEWER, "AseguradoraDemo", "Demo1234!"),
]

# Orden de inserción que respeta las FKs
INSERT_ORDER = [
    Tenant, TenantSettings, Agent, Queue, AgentPerformanceQueue, AgentPerformance,
    Chat, ChatDetail, ChatVariable, ChatTag, AgentMetric,
    Message, MessageContent, MessageButton, MessageMedia, MessageFile,
]


def _rand_dt(rng: random.Random) -> datetime:
    return DATE_START + timedelta(minutes=rng.randrange(SPAN_MINUTES))


def _agents_for(tenant_id: str) -> list[dict]:
    domain = tenant_id.lower()
    base = [
        ("Ana Gómez", "agent"), ("Carlos Ruiz", "agent"), ("Lucía Fernández", "supervisor"),
        ("Martín López", "agent"), ("Paula Sosa", "agent"), ("Diego Martínez", "agent"),
    ]
    out = []
    for i, (name, role) in enumerate(base, start=1):
        first = name.split()[0].lower().replace("í", "i").replace("ú", "u")
        out.append({
            "email": f"{first}.{i}@{domain}.com",
            "name": name,
            "agent_id": f"AG{i:03d}",
            "role": role,
        })
    return out


def _purge_tenant(db: Session, tenant_id: str) -> None:
    for model in (
        MessageFile, MessageMedia, MessageButton, MessageContent, Message,
        ChatTag, ChatVariable, ChatDetail, AgentMetric, AgentPerformance,
        AgentPerformanceQueue, Chat, Queue, Agent,
        EtlControl, EtlRun, RetryJob, BackupJob, AuditLog, TenantSettings,
    ):
        db.execute(delete(model).where(model.tenant_id == tenant_id))
    db.execute(delete(User).where(User.tenant_id == tenant_id))
    db.execute(delete(Tenant).where(Tenant.tenant_id == tenant_id))


def _upload_seed_file(s3, bucket: str, key: str, body: bytes, content_type: str) -> None:
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    except Exception:
        pass  # sin S3 en dev el seed sigue sirviendo para la DB


def generate_tenant_rows(cfg: dict, s3=None, bucket: str = "") -> dict[type, list[dict]]:
    """Genera todas las filas del tenant como dicts por modelo."""
    rng = random.Random(cfg["seed"])
    t = cfg["tenant_id"]
    rows: dict[type, list[dict]] = {model: [] for model in INSERT_ORDER}

    rows[Tenant].append({"tenant_id": t, "tenant_name": cfg["tenant_name"], "created_at": DATE_START})
    rows[TenantSettings].append({
        "tenant_id": t,
        "etl_schedule_cron": "0 3 * * *",
        "etl_initial_ts": DATE_START,
        "etl_window_days": 30,
        "is_etl_enabled": False,
        "siniestros_queue": "Siniestros",
        "siniestros_button": "Denunciar siniestro",
    })

    agents = _agents_for(t)
    for a in agents:
        rows[Agent].append({
            "tenant_id": t, "agent_email": a["email"], "agent_name": a["name"], "role": a["role"],
        })
    for q in QUEUES:
        rows[Queue].append({"tenant_id": t, "queue": q})
    for a in agents:
        for q in QUEUES:
            rows[AgentPerformanceQueue].append({"tenant_id": t, "agent_email": a["email"], "queue": q})
        for _ in range(8):
            ci = _rand_dt(rng)
            rows[AgentPerformance].append({
                "tenant_id": t, "agent_email": a["email"],
                "state": rng.choice(["online", "away", "online"]),
                "checkin": ci, "checkout": ci + timedelta(minutes=420 + rng.randrange(120)),
            })

    msg_seq = 0
    for i in range(1, cfg["num_chats"] + 1):
        chat_id = f"{cfg['phone_prefix']}{500000 + i:06d}"
        created = _rand_dt(rng)
        first_name = rng.choice(NOMBRES)
        last_name = rng.choice(APELLIDOS)

        rows[Chat].append({
            "tenant_id": t, "chat_id": chat_id, "channel_id": "whatsapp", "contact_id": chat_id,
        })
        rows[ChatDetail].append({
            "tenant_id": t, "chat_id": chat_id, "creation_time": created,
            "last_session_creation_time": created, "first_name": first_name,
            "last_name": last_name, "country": "AR",
            "email": f"{first_name.lower()}.{last_name.lower()}@example.com",
            "is_tester": False, "is_bot_muted": False, "is_banned": False,
        })
        rows[ChatVariable].append({
            "tenant_id": t, "chat_id": chat_id, "var_key": "poliza",
            "var_value": f"POL-{rng.randrange(10000, 99999)}",
        })
        rows[ChatVariable].append({
            "tenant_id": t, "chat_id": chat_id, "var_key": "tipo_seguro",
            "var_value": rng.choice(TIPOS_SEGURO),
        })
        for tag in rng.sample(TAGS, k=rng.randrange(0, 3)):
            rows[ChatTag].append({"tenant_id": t, "chat_id": chat_id, "tag": tag})

        # 1 a 3 sesiones por chat
        for s in range(rng.randrange(1, 4)):
            session_created = created + timedelta(days=rng.randrange(0, 30), minutes=rng.randrange(600))
            if session_created >= DATE_END:
                session_created = created
            session_id = f"{chat_id}-S{s + 1}"
            with_agent = rng.random() > 0.35  # ~35% de sesiones sin agente
            agent = rng.choice(agents) if with_agent else None
            queue = rng.choice(QUEUES)
            is_closed = rng.random() > 0.15
            first_resp_secs = rng.randrange(30, 1800) if with_agent and is_closed else (0 if with_agent else None)

            rows[AgentMetric].append({
                "tenant_id": t, "session_id": session_id, "chat_id": chat_id,
                "session_creation_time": session_created,
                "queue": queue,
                "agent_name": agent["name"] if agent else None,
                "agent_id": agent["agent_id"] if agent else None,
                "typification": rng.choice(TIPIFICACIONES),
                "closed_time": session_created + timedelta(minutes=rng.randrange(10, 240)) if is_closed else None,
                "open_sessions": 0 if is_closed else 1,
                "closed_sessions": 1 if is_closed else 0,
                "operator_responses": rng.randrange(1, 15) if with_agent else 0,
                # sesiones abiertas → métricas NULL; promedios deben excluir NULL y ceros
                "from_op_assigned_to_op_first_response": first_resp_secs,
                "from_queue_asign_to_op_assigned": rng.randrange(10, 600) if with_agent and is_closed else None,
                "avg_response_time": rng.randrange(20, 300) if is_closed else None,
            })

            # mensajes de la sesión
            started_by_external = rng.random() > 0.3
            n_msgs = rng.randrange(3, 13)
            msg_time = session_created
            for m in range(n_msgs):
                msg_seq += 1
                mid = f"{t[:3].upper()}-{msg_seq:08d}"
                msg_time = msg_time + timedelta(seconds=rng.randrange(20, 600))
                if m == 0:
                    sender = "user" if started_by_external else "bot"
                else:
                    sender = rng.choice(["user", "bot"] + (["agent"] if with_agent else []))
                is_template = sender == "bot" and m == 0 and not started_by_external and rng.random() > 0.5
                template = rng.choice(TEMPLATES) if is_template else None

                rows[Message].append({
                    "tenant_id": t, "id": mid, "creation_time": msg_time, "message_from": sender,
                    "agent_id": agent["agent_id"] if (agent and sender == "agent") else None,
                    "queue_id": queue, "session_creation_time": session_created,
                    "chat_id": chat_id, "session_id": session_id,
                    "whatsapp_template_name": template,
                })

                has_media = sender == "user" and rng.random() < 0.12
                has_audio = sender == "user" and not has_media and rng.random() < 0.08
                shows_buttons = sender == "bot" and m == 1
                selected = rng.choice(BUTTONS_MENU) if (sender == "user" and m == 2 and rng.random() > 0.4) else None

                content_type = "image" if has_media else ("audio" if has_audio else "text")
                rows[MessageContent].append({
                    "tenant_id": t, "message_id": mid, "content_type": content_type,
                    "text": _sample_text(rng, sender, selected),
                    "selected_button": selected,
                    "original_text": None,
                    "original_audio_url": f"https://storage.botmaker.com/{t}/{mid}.wav" if has_audio else None,
                })
                if shows_buttons:
                    for b in BUTTONS_MENU:
                        rows[MessageButton].append({"tenant_id": t, "message_id": mid, "button": b})

                for kind, has in (("media", has_media), ("audio", has_audio)):
                    if not has:
                        continue
                    fname = f"{mid}.png" if kind == "media" else f"{mid}.wav"
                    url = f"https://storage.botmaker.com/{t}/{fname}"
                    if kind == "media":
                        rows[MessageMedia].append({
                            "tenant_id": t, "message_id": mid, "caption": None, "url": url,
                        })
                    # ~80% ok, resto distribuye estados de fallo
                    roll = rng.random()
                    if roll < 0.8:
                        status, s3_key = "ok", f"tenants/{t}/files/{mid}/{kind}/{fname}"
                        if s3 is not None:
                            body = TINY_PNG if kind == "media" else TINY_WAV
                            ctype = "image/png" if kind == "media" else "audio/wav"
                            _upload_seed_file(s3, bucket, s3_key, body, ctype)
                    elif roll < 0.9:
                        status, s3_key = "forbidden", None
                    elif roll < 0.96:
                        status, s3_key = "not_found", None
                    else:
                        status, s3_key = "error", None
                    ok = status == "ok"
                    rows[MessageFile].append({
                        "tenant_id": t, "message_id": mid, "file_type": kind, "original_url": url,
                        "s3_key": s3_key, "downloaded_at": msg_time, "status": status,
                        "size_bytes": (len(TINY_PNG) if kind == "media" else len(TINY_WAV)) if ok else None,
                        "content_type": ("image/png" if kind == "media" else "audio/wav") if ok else None,
                    })

    return rows


def _sample_text(rng: random.Random, sender: str, selected: str | None) -> str:
    if selected:
        return selected
    user_msgs = [
        "Hola, quiero denunciar un siniestro", "Necesito cotizar un seguro para mi auto",
        "¿Cuándo vence mi cuota?", "Tuve un choque en la esquina de mi casa",
        "Me cayó granizo en el techo", "Gracias por la atención", "¿Me pueden llamar?",
    ]
    bot_msgs = [
        "¡Hola! Soy el asistente virtual. ¿En qué puedo ayudarte?",
        "Selecciona una opción del menú", "Un agente te atenderá en breve",
        "Tu consulta fue registrada con éxito",
    ]
    agent_msgs = [
        "Buenas tardes, soy tu asesor. ¿En qué puedo ayudarte?",
        "Ya registré la denuncia, te paso el número de trámite",
        "Te envío la cotización por este medio", "Quedo a disposición, ¡saludos!",
    ]
    return rng.choice({"user": user_msgs, "bot": bot_msgs, "agent": agent_msgs}[sender])


def seed_tenant(db: Session, cfg: dict, s3=None, bucket: str = "") -> None:
    _purge_tenant(db, cfg["tenant_id"])
    rows = generate_tenant_rows(cfg, s3=s3, bucket=bucket)
    for model in INSERT_ORDER:
        if rows[model]:
            db.execute(insert(model), rows[model])


def seed_users(db: Session) -> None:
    for email, full_name, role, tenant_id, password in USERS:
        existing = db.scalar(select(User).where(User.email == email))
        if existing is None:
            db.add(User(
                tenant_id=tenant_id, email=email, password_hash=hash_password(password),
                full_name=full_name, role=role, is_active=True,
            ))
    db.flush()


def make_s3_client():
    settings = get_settings()
    if not settings.s3_access_key:
        return None
    try:
        import boto3

        s3 = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
        s3.head_bucket(Bucket=settings.s3_bucket)
        return s3
    except Exception:
        return None


def run(if_empty: bool = False) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    s3 = make_s3_client()
    with Session(engine) as db:
        if if_empty and db.scalar(select(Tenant.tenant_id).limit(1)) is not None:
            print("Seed omitido: ya existen tenants.")
            return
        for cfg in TENANTS:
            print(f"Sembrando tenant {cfg['tenant_id']}…")
            seed_tenant(db, cfg, s3=s3, bucket=settings.s3_bucket)
        seed_users(db)
        db.commit()
    print("Seed completado: 2 tenants con ~300 chats cada uno.")
    print("Usuarios: " + ", ".join(u[0] for u in USERS))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--if-empty", action="store_true",
                        help="solo siembra si la base está vacía")
    args = parser.parse_args()
    try:
        run(if_empty=args.if_empty)
    except Exception as e:
        print(f"Error en seed: {e}", file=sys.stderr)
        raise
