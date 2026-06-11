"""Etapas del ETL por tenant (port de etl_botmaker_logs.py, §6).

Orden: agent_performance → agent_metrics (open+closed) → messages + subtablas →
chat_details + variables + tags. Cada etapa actualiza su last_ts al cerrar OK.
Upserts idempotentes con ON CONFLICT (reemplazan los MERGE / IF NOT EXISTS legacy).
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

import requests
from dateutil import parser as dtparser
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AgentMetric,
    AgentPerformance,
    AgentPerformanceQueue,
    Chat,
    ChatDetail,
    ChatTag,
    ChatVariable,
    EncryptionParams,
    Message,
    MessageButton,
    MessageCall,
    MessageCarouselItem,
    MessageContent,
    MessageFile,
    MessageLocation,
    MessageMedia,
    Queue,
)
from worker.etl.botmaker import (
    URL_AGENT_METRICS,
    URL_AGENT_PERF,
    URL_CHAT,
    URL_MESSAGES,
    BotmakerClient,
)
from worker.etl.control import get_last_ts, get_window, iso_z, iso_z_ms, set_last_ts
from worker.etl.files import download_to_s3

logger = logging.getLogger("koala.worker.stages")


def parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    try:
        dt = dtparser.isoparse(ts_str)
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


@dataclass
class StageContext:
    tenant_id: str
    client: BotmakerClient
    s3: object
    bucket: str
    initial_ts: datetime | None
    window_days: int
    now: datetime | None = None
    stats: dict = field(default_factory=dict)


def _insert_ignore(db: Session, model, values: dict) -> None:
    db.execute(pg_insert(model).values(**values).on_conflict_do_nothing())


def _upsert(db: Session, model, values: dict, pk_cols: list[str]) -> None:
    stmt = pg_insert(model).values(**values)
    update_cols = {k: stmt.excluded[k] for k in values if k not in pk_cols}
    db.execute(stmt.on_conflict_do_update(index_elements=pk_cols, set_=update_cols))


def _ensure_queue(db: Session, tenant_id: str, queue: str | None) -> None:
    if queue:
        _insert_ignore(db, Queue, {"tenant_id": tenant_id, "queue": queue})


def _ensure_chat(db: Session, tenant_id: str, chat_id: str | None) -> None:
    if chat_id:
        _insert_ignore(db, Chat, {"tenant_id": tenant_id, "chat_id": chat_id})


# ——————————————————————————————————————————————————————————————
# Etapa 1: agent_performance (+ agents, queues, relación M–N)
# ——————————————————————————————————————————————————————————————

def stage_agent_performance(db: Session, ctx: StageContext) -> dict:
    last = get_last_ts(db, ctx.tenant_id, "agent-performance")
    from_dt, to_dt = get_window(
        last, initial_ts=ctx.initial_ts, window_days=ctx.window_days, now=ctx.now
    )
    data = ctx.client.fetch_all(
        URL_AGENT_PERF, {"from": iso_z(from_dt), "to": iso_z(to_dt)}
    )
    logger.info("[%s] agent-performance: %d registros", ctx.tenant_id, len(data))

    count = 0
    for a in data:
        agent_email = a.get("agentEmail")
        if not agent_email:
            continue
        _insert_ignore(db, Agent, {
            "tenant_id": ctx.tenant_id, "agent_email": agent_email,
            "agent_name": a.get("agentName") or agent_email,
            "role": a.get("role") or "agent",
        })
        for queue in a.get("queue") or []:
            _ensure_queue(db, ctx.tenant_id, queue)
            _insert_ignore(db, AgentPerformanceQueue, {
                "tenant_id": ctx.tenant_id, "agent_email": agent_email, "queue": queue,
            })

        checkin, checkout = parse_ts(a.get("checkin")), parse_ts(a.get("checkout"))
        # sin PK natural: evita duplicados por (tenant, email, checkin, checkout)
        exists = db.scalar(
            select(AgentPerformance.performance_id).where(
                (AgentPerformance.tenant_id == ctx.tenant_id)
                & (AgentPerformance.agent_email == agent_email)
                & (AgentPerformance.checkin == checkin)
                & (AgentPerformance.checkout == checkout)
            ).limit(1)
        )
        if exists is None:
            db.add(AgentPerformance(
                tenant_id=ctx.tenant_id, agent_email=agent_email,
                state=a.get("state"), checkin=checkin, checkout=checkout,
            ))
        count += 1

    if data:
        set_last_ts(db, ctx.tenant_id, "agent-performance", to_dt)
    return {"rows": count, "window": [iso_z(from_dt), iso_z(to_dt)]}


# ——————————————————————————————————————————————————————————————
# Etapa 2: agent_metrics (open + closed — §11.5)
# ——————————————————————————————————————————————————————————————

AGENT_METRIC_FIELDS = {
    "chat_id": "chatId",
    "avg_attending_time": "avgAttendingTime",
    "avg_response_time": "avgResponseTime",
    "queue": "queue",
    "agent_name": "agentName",
    "agent_id": "agentId",
    "typification": "typification",
    "open_sessions": "openSessions",
    "closed_sessions": "closedSessions",
    "on_hold": "onHold",
    "op_response_time": "opResponseTime",
    "operator_responses": "operatorResponses",
    "session_transfer_in": "sessionTransferIn",
    "session_transfer_out": "sessionTransferOut",
    "session_transfer_out_no_messages": "sessionTransferOutNoMessages",
    "closed_with_no_messages": "closedWithNoMessages",
    "timeout_no_messages": "timeoutNoMessages",
    "agent_timeout": "agentTimeout",
    "user_timeout": "userTimeout",
    "from_queue_asign_to_op_assigned": "fromQueueAsignToOpAssigned",
    "from_session_start_to_op_first_response": "fromSessionStartToOpFirstResponse",
    "from_queue_asign_to_op_first_response": "fromQueueAsignToOpFirstResponse",
    "from_op_assigned_to_op_first_response": "fromOpAssignedToOpFirstResponse",
    "from_queue_asign_to_session_closed": "fromQueueAsignToSessionClosed",
    "from_op_assignation_to_session_closed": "fromOpAssignationToSessionClosed",
    "session_timeout": "sessionTimeout",
    "conversation_link": "conversationLink",
}


def stage_agent_metrics(db: Session, ctx: StageContext) -> dict:
    last = get_last_ts(db, ctx.tenant_id, "agent-metrics")
    from_dt, to_dt = get_window(
        last, initial_ts=ctx.initial_ts, window_days=ctx.window_days, now=ctx.now
    )

    all_items: list[dict] = []
    for session_status in ("open", "closed"):  # hay que pedir las dos (§11.5)
        all_items.extend(ctx.client.fetch_all(URL_AGENT_METRICS, {
            "from": iso_z_ms(from_dt),
            "to": iso_z_ms(to_dt),
            "session-status": session_status,
        }))
    logger.info("[%s] agent-metrics: %d registros", ctx.tenant_id, len(all_items))

    count = 0
    for s in all_items:
        session_id = s.get("sessionId")
        if not session_id:
            continue
        _ensure_queue(db, ctx.tenant_id, s.get("queue"))
        _ensure_chat(db, ctx.tenant_id, s.get("chatId"))

        values = {
            "tenant_id": ctx.tenant_id,
            "session_id": session_id,
            "session_creation_time": parse_ts(s.get("sessionCreationTime")),
            "closed_time": parse_ts(s.get("closedTime")),
        }
        values.update({col: s.get(api) for col, api in AGENT_METRIC_FIELDS.items()})
        _upsert(db, AgentMetric, values, ["tenant_id", "session_id"])
        count += 1

    if all_items:
        set_last_ts(db, ctx.tenant_id, "agent-metrics", to_dt)
    return {"rows": count, "window": [iso_z(from_dt), iso_z(to_dt)]}


# ——————————————————————————————————————————————————————————————
# Etapa 3: messages + subtablas (+ descarga de archivos a S3)
# ——————————————————————————————————————————————————————————————

def _upsert_message_file(
    db: Session, ctx: StageContext, *, message_id: str, file_type: str, url: str
) -> str:
    result = download_to_s3(
        ctx.client, ctx.s3, ctx.bucket,
        url=url, tenant_id=ctx.tenant_id, message_id=message_id, file_type=file_type,
    )
    _upsert(db, MessageFile, {
        "tenant_id": ctx.tenant_id,
        "message_id": message_id,
        "file_type": file_type,
        "original_url": url[:500],
        "s3_key": result.s3_key,
        "downloaded_at": datetime.now(UTC),
        "status": result.status,
        "size_bytes": result.size_bytes,
        "content_type": result.content_type,
    }, ["tenant_id", "message_id", "file_type"])
    return result.status


def stage_messages(db: Session, ctx: StageContext) -> dict:
    last = get_last_ts(db, ctx.tenant_id, "messages")
    from_dt, to_dt = get_window(
        last, initial_ts=ctx.initial_ts, window_days=ctx.window_days, now=ctx.now
    )
    if from_dt >= to_dt:
        logger.info("[%s] ventana de messages vacía", ctx.tenant_id)
        return {"rows": 0}

    data = ctx.client.fetch_all(URL_MESSAGES, {
        "from": iso_z_ms(from_dt),
        "to": iso_z_ms(to_dt),
        "limit": 1500,
        "long-term-search": True,
    })
    logger.info("[%s] messages: %d mensajes", ctx.tenant_id, len(data))

    count = files_ok = files_failed = 0
    for m in data:
        mid = m.get("id")
        if not mid:
            continue
        chat = m.get("chat") or {}
        chat_id = chat.get("chatId")
        content = m.get("content") or {}

        if chat_id:
            _upsert(db, Chat, {
                "tenant_id": ctx.tenant_id, "chat_id": chat_id,
                "channel_id": chat.get("channelId"), "contact_id": chat.get("contactId"),
            }, ["tenant_id", "chat_id"])
        _ensure_queue(db, ctx.tenant_id, m.get("queueId"))

        _upsert(db, Message, {
            "tenant_id": ctx.tenant_id,
            "id": mid,
            "creation_time": parse_ts(m.get("creationTime")),
            "message_from": m.get("from"),
            "agent_id": m.get("agentId"),
            "queue_id": m.get("queueId"),
            "session_creation_time": parse_ts(m.get("sessionCreationTime")),
            "chat_id": chat_id,
            "session_id": m.get("sessionId"),
            "whatsapp_template_name": content.get("whatsAppTemplateName"),
        }, ["tenant_id", "id"])

        _upsert(db, MessageContent, {
            "tenant_id": ctx.tenant_id,
            "message_id": mid,
            "content_type": content.get("type"),
            "text": content.get("text"),
            "selected_button": content.get("selectedButton"),
            "original_text": content.get("originalText"),
            "original_audio_url": content.get("originalAudioUrl"),
        }, ["tenant_id", "message_id"])

        for btn in content.get("buttons") or []:
            _insert_ignore(db, MessageButton, {
                "tenant_id": ctx.tenant_id, "message_id": mid, "button": btn,
            })

        for item in content.get("carouselItems") or []:
            exists = db.scalar(
                select(MessageCarouselItem.item_index).where(
                    (MessageCarouselItem.tenant_id == ctx.tenant_id)
                    & (MessageCarouselItem.message_id == mid)
                    & (MessageCarouselItem.carousel_item == item)
                ).limit(1)
            )
            if exists is None:
                db.add(MessageCarouselItem(
                    tenant_id=ctx.tenant_id, message_id=mid, carousel_item=item,
                ))

        media = content.get("media")
        if media and media.get("url"):
            url = media["url"]
            exists = db.scalar(
                select(MessageMedia.media_id).where(
                    (MessageMedia.tenant_id == ctx.tenant_id) & (MessageMedia.url == url)
                ).limit(1)
            )
            if exists is None:
                db.add(MessageMedia(
                    tenant_id=ctx.tenant_id, message_id=mid,
                    caption=media.get("caption"), url=url,
                ))
            try:
                status = _upsert_message_file(
                    db, ctx, message_id=mid, file_type="media", url=url
                )
                files_ok += status == "ok"
                files_failed += status != "ok"
            except Exception:
                # nunca frenar la etapa por un archivo (§6.5)
                logger.exception("[%s] fallo procesando media de %s", ctx.tenant_id, mid)
                files_failed += 1

        loc = content.get("location")
        if loc:
            _insert_ignore(db, MessageLocation, {
                "tenant_id": ctx.tenant_id, "message_id": mid,
                "latitude": loc.get("latitude"), "longitude": loc.get("longitude"),
                "name": loc.get("name"), "address": loc.get("address"),
            })

        call = content.get("call")
        if call:
            _insert_ignore(db, MessageCall, {
                "tenant_id": ctx.tenant_id, "message_id": mid, "event": call.get("event"),
            })

        audio_url = content.get("originalAudioUrl")
        if audio_url:
            try:
                status = _upsert_message_file(
                    db, ctx, message_id=mid, file_type="audio", url=audio_url
                )
                files_ok += status == "ok"
                files_failed += status != "ok"
            except Exception:
                logger.exception("[%s] fallo procesando audio de %s", ctx.tenant_id, mid)
                files_failed += 1

        ep = m.get("encryptionParams")
        if ep:
            _insert_ignore(db, EncryptionParams, {
                "tenant_id": ctx.tenant_id, "message_id": mid,
                "version": ep.get("version"), "config_id": ep.get("configId"),
                "timestamp": ep.get("timestamp"), "encrypted_key": ep.get("encryptedKey"),
            })

        count += 1

    if data:
        set_last_ts(db, ctx.tenant_id, "messages", to_dt)
    return {
        "rows": count, "files_ok": files_ok, "files_failed": files_failed,
        "window": [iso_z(from_dt), iso_z(to_dt)],
    }


# ——————————————————————————————————————————————————————————————
# Etapa 4: chat_details + variables + tags
# ——————————————————————————————————————————————————————————————

def stage_chat_details(db: Session, ctx: StageContext) -> dict:
    missing = list(db.scalars(
        select(Chat.chat_id)
        .outerjoin(
            ChatDetail,
            (ChatDetail.tenant_id == Chat.tenant_id) & (ChatDetail.chat_id == Chat.chat_id),
        )
        .where((Chat.tenant_id == ctx.tenant_id) & (ChatDetail.chat_id.is_(None)))
    ))
    logger.info("[%s] chat_details: %d chats pendientes", ctx.tenant_id, len(missing))

    count = 0
    for cid in missing:
        try:
            resp = ctx.client.request("GET", URL_CHAT.format(cid))
        except requests.HTTPError as e:
            if getattr(e.response, "status_code", None) == 404:
                logger.warning("[%s] chat %s no encontrado (404), se omite", ctx.tenant_id, cid)
                continue
            raise
        chat = resp.json().get("chat") or {}

        _insert_ignore(db, ChatDetail, {
            "tenant_id": ctx.tenant_id,
            "chat_id": cid,
            "creation_time": parse_ts(chat.get("creationTime")),
            "last_session_creation_time": parse_ts(chat.get("lastSessionCreationTime")),
            "external_id": chat.get("externalId"),
            "first_name": chat.get("firstName"),
            "last_name": chat.get("lastName"),
            "country": chat.get("country"),
            "email": chat.get("email"),
            "whatsapp_window_close_datetime": parse_ts(chat.get("whatsAppWindowCloseDatetime")),
            "queue_id": chat.get("queueId"),
            "agent_id": chat.get("agentId"),
            "on_hold_agent_id": chat.get("onHoldAgentId"),
            "last_user_message_datetime": parse_ts(chat.get("lastUserMessageDatetime")),
            "is_tester": bool(chat.get("isTester", False)),
            "is_bot_muted": bool(chat.get("isBotMuted", False)),
            "is_banned": bool(chat.get("isBanned", False)),
        })
        for key, val in (chat.get("variables") or {}).items():
            _insert_ignore(db, ChatVariable, {
                "tenant_id": ctx.tenant_id, "chat_id": cid,
                "var_key": key[:100], "var_value": str(val) if val is not None else None,
            })
        for tag in chat.get("tags") or []:
            _insert_ignore(db, ChatTag, {
                "tenant_id": ctx.tenant_id, "chat_id": cid, "tag": tag[:100],
            })
        count += 1

    return {"rows": count}
