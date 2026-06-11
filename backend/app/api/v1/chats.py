"""Visor de conversaciones (§7.2): lista de chats, detalle y timeline paginado."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUserDep, DbDep, TenantScopeDep
from app.models import (
    Chat,
    ChatDetail,
    ChatTag,
    ChatVariable,
    Message,
    MessageButton,
    MessageContent,
    MessageFile,
    MessageLocation,
)
from app.schemas.chats import (
    ChatDetailOut,
    ChatListItem,
    ChatListOut,
    ChatMessagesOut,
    MessageFileOut,
    MessageOut,
)
from app.services.audit import audit

router = APIRouter(prefix="/chats", tags=["chats"])


@router.get("", response_model=ChatListOut)
async def list_chats(
    db: DbDep,
    current: CurrentUserDep,
    tenant: TenantScopeDep,
    search: Annotated[str | None, Query()] = None,
    date_from: Annotated[datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime | None, Query(alias="to")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 30,
):
    last_msg = (
        select(
            Message.chat_id,
            func.max(Message.creation_time).label("last_time"),
        )
        .where(Message.tenant_id == tenant)
        .group_by(Message.chat_id)
        .subquery()
    )

    query = (
        select(Chat, ChatDetail, last_msg.c.last_time)
        .join(ChatDetail, (ChatDetail.tenant_id == Chat.tenant_id) & (ChatDetail.chat_id == Chat.chat_id), isouter=True)
        .join(last_msg, last_msg.c.chat_id == Chat.chat_id, isouter=True)
        .where(Chat.tenant_id == tenant)
    )

    if search:
        term = f"%{search.strip()}%"
        query = query.where(or_(
            Chat.chat_id.ilike(term),
            ChatDetail.first_name.ilike(term),
            ChatDetail.last_name.ilike(term),
            func.concat(ChatDetail.first_name, " ", ChatDetail.last_name).ilike(term),
        ))
    if date_from is not None:
        query = query.where(last_msg.c.last_time >= date_from)
    if date_to is not None:
        query = query.where(last_msg.c.last_time <= date_to)

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = (
        await db.execute(
            query.order_by(last_msg.c.last_time.desc().nulls_last())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    chat_ids = [r[0].chat_id for r in rows]
    tags_by_chat: dict[str, list[str]] = {}
    previews: dict[str, str] = {}
    if chat_ids:
        tag_rows = await db.execute(
            select(ChatTag.chat_id, ChatTag.tag).where(
                (ChatTag.tenant_id == tenant) & ChatTag.chat_id.in_(chat_ids)
            )
        )
        for chat_id, tag in tag_rows:
            tags_by_chat.setdefault(chat_id, []).append(tag)

        # último texto por chat (para preview de la lista)
        preview_rows = await db.execute(
            select(Message.chat_id, MessageContent.text, Message.creation_time)
            .join(MessageContent, (MessageContent.tenant_id == Message.tenant_id) & (MessageContent.message_id == Message.id))
            .where((Message.tenant_id == tenant) & Message.chat_id.in_(chat_ids))
            .order_by(Message.chat_id, Message.creation_time.desc())
            .distinct(Message.chat_id)
        )
        for chat_id, text, _ in preview_rows:
            previews[chat_id] = (text or "")[:120]

    items = [
        ChatListItem(
            chat_id=chat.chat_id,
            contact_id=chat.contact_id,
            first_name=detail.first_name if detail else None,
            last_name=detail.last_name if detail else None,
            last_message_time=last_time,
            last_message_preview=previews.get(chat.chat_id),
            tags=tags_by_chat.get(chat.chat_id, []),
        )
        for chat, detail, last_time in rows
    ]
    return ChatListOut(total=total, page=page, page_size=page_size, items=items)


async def _get_chat_or_404(db, tenant: str, chat_id: str) -> Chat:
    chat = await db.get(Chat, (tenant, chat_id))
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat inexistente")
    return chat


@router.get("/{chat_id}", response_model=ChatDetailOut)
async def get_chat(chat_id: str, db: DbDep, current: CurrentUserDep, tenant: TenantScopeDep):
    chat = await _get_chat_or_404(db, tenant, chat_id)
    detail = await db.get(ChatDetail, (tenant, chat_id))
    variables = {
        k: v
        for k, v in await db.execute(
            select(ChatVariable.var_key, ChatVariable.var_value).where(
                (ChatVariable.tenant_id == tenant) & (ChatVariable.chat_id == chat_id)
            )
        )
    }
    tags = list(
        await db.scalars(
            select(ChatTag.tag).where(
                (ChatTag.tenant_id == tenant) & (ChatTag.chat_id == chat_id)
            )
        )
    )
    return ChatDetailOut(
        chat_id=chat.chat_id,
        contact_id=chat.contact_id,
        channel_id=chat.channel_id,
        first_name=detail.first_name if detail else None,
        last_name=detail.last_name if detail else None,
        email=detail.email if detail else None,
        country=detail.country if detail else None,
        creation_time=detail.creation_time if detail else None,
        last_session_creation_time=detail.last_session_creation_time if detail else None,
        variables=variables,
        tags=tags,
    )


@router.get("/{chat_id}/messages", response_model=ChatMessagesOut)
async def get_chat_messages(
    chat_id: str,
    db: DbDep,
    current: CurrentUserDep,
    tenant: TenantScopeDep,
    before: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Paginado hacia atrás estilo chat: trae los `limit` mensajes anteriores a `before`."""
    await _get_chat_or_404(db, tenant, chat_id)

    query = (
        select(Message, MessageContent)
        .join(
            MessageContent,
            (MessageContent.tenant_id == Message.tenant_id) & (MessageContent.message_id == Message.id),
            isouter=True,
        )
        .where((Message.tenant_id == tenant) & (Message.chat_id == chat_id))
    )
    if before is not None:
        query = query.where(Message.creation_time < before)

    rows = (
        await db.execute(query.order_by(Message.creation_time.desc()).limit(limit + 1))
    ).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    rows.reverse()  # ascendente para render

    msg_ids = [m.id for m, _ in rows]
    buttons: dict[str, list[str]] = {}
    files: dict[str, list[MessageFileOut]] = {}
    locations: dict[str, dict] = {}
    agent_names: dict[str, str] = {}
    if msg_ids:
        for mid, btn in await db.execute(
            select(MessageButton.message_id, MessageButton.button).where(
                (MessageButton.tenant_id == tenant) & MessageButton.message_id.in_(msg_ids)
            )
        ):
            buttons.setdefault(mid, []).append(btn)
        for mf in await db.scalars(
            select(MessageFile).where(
                (MessageFile.tenant_id == tenant) & MessageFile.message_id.in_(msg_ids)
            )
        ):
            files.setdefault(mf.message_id, []).append(MessageFileOut(
                file_type=mf.file_type,
                status=mf.status,
                content_type=mf.content_type,
                size_bytes=mf.size_bytes,
                has_file=mf.status == "ok" and mf.s3_key is not None,
            ))
        for loc in await db.scalars(
            select(MessageLocation).where(
                (MessageLocation.tenant_id == tenant) & MessageLocation.message_id.in_(msg_ids)
            )
        ):
            locations[loc.message_id] = {
                "latitude": loc.latitude, "longitude": loc.longitude,
                "name": loc.name, "address": loc.address,
            }
        # nombre del agente para las burbujas
        agent_ids = {m.agent_id for m, _ in rows if m.agent_id}
        if agent_ids:
            from app.models import AgentMetric

            for aid, aname in await db.execute(
                select(AgentMetric.agent_id, func.max(AgentMetric.agent_name))
                .where((AgentMetric.tenant_id == tenant) & AgentMetric.agent_id.in_(agent_ids))
                .group_by(AgentMetric.agent_id)
            ):
                if aname:
                    agent_names[aid] = aname

    items = [
        MessageOut(
            id=m.id,
            creation_time=m.creation_time,
            message_from=m.message_from,
            agent_id=m.agent_id,
            agent_name=agent_names.get(m.agent_id) if m.agent_id else None,
            session_id=m.session_id,
            session_creation_time=m.session_creation_time,
            queue_id=m.queue_id,
            whatsapp_template_name=m.whatsapp_template_name,
            content_type=c.content_type if c else None,
            text=c.text if c else None,
            selected_button=c.selected_button if c else None,
            buttons=buttons.get(m.id, []),
            files=files.get(m.id, []),
            location=locations.get(m.id),
        )
        for m, c in rows
    ]

    # Auditoría de visualización de conversaciones (§8.5) — sin contenido sensible
    await audit(db, action="chat_viewed", tenant_id=tenant, user_id=current.id,
                entity="chat", entity_id=chat_id)
    await db.commit()

    return ChatMessagesOut(
        chat_id=chat_id,
        items=items,
        has_more=has_more,
        next_before=items[0].creation_time if items and has_more else None,
    )
