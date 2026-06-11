from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ChatListItem(BaseModel):
    chat_id: str
    contact_id: str | None
    first_name: str | None
    last_name: str | None
    last_message_time: datetime | None
    last_message_preview: str | None
    tags: list[str] = []


class ChatListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ChatListItem]


class ChatDetailOut(BaseModel):
    chat_id: str
    contact_id: str | None
    channel_id: str | None
    first_name: str | None
    last_name: str | None
    email: str | None
    country: str | None
    creation_time: datetime | None
    last_session_creation_time: datetime | None
    variables: dict[str, str | None]
    tags: list[str]


class MessageFileOut(BaseModel):
    file_type: str
    status: str
    content_type: str | None
    size_bytes: int | None
    has_file: bool  # status == ok y s3_key presente


class MessageOut(BaseModel):
    id: str
    creation_time: datetime | None
    message_from: str | None
    agent_id: str | None
    agent_name: str | None = None
    session_id: str | None
    session_creation_time: datetime | None
    queue_id: str | None
    whatsapp_template_name: str | None
    content_type: str | None = None
    text: str | None = None
    selected_button: str | None = None
    buttons: list[str] = []
    files: list[MessageFileOut] = []
    location: dict[str, Any] | None = None


class ChatMessagesOut(BaseModel):
    chat_id: str
    items: list[MessageOut]  # ascendente por fecha
    has_more: bool
    next_before: datetime | None  # cursor para paginar hacia atrás
