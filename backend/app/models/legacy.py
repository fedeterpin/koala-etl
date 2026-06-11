"""Port a PostgreSQL del esquema legacy de SQL Server (18 tablas).

Conversiones aplicadas (ver PLAN-APP.md §5.1):
- NVARCHAR(n) -> VARCHAR(n) / TEXT, DATETIME2 -> TIMESTAMPTZ (UTC), BIT -> BOOLEAN,
  INT IDENTITY -> BIGINT GENERATED ALWAYS AS IDENTITY.
- Identificadores camelCase -> snake_case.
- message_files: file_path -> s3_key (nullable) + status con CHECK + size_bytes + content_type.
- Las columnas calculadas "_arg" NO se portan: las fechas se guardan en UTC y la conversión
  a hora argentina se hace en queries (AT TIME ZONE) o en presentación.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

UTCTimestamp = TIMESTAMP(timezone=True)

FILE_STATUSES = ("ok", "forbidden", "not_found", "error", "skipped")


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(UTCTimestamp)


class Agent(Base):
    __tablename__ = "agents"

    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.tenant_id"), primary_key=True
    )
    agent_email: Mapped[str] = mapped_column(String(255), primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)


class Queue(Base):
    __tablename__ = "queues"

    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.tenant_id"), primary_key=True
    )
    queue: Mapped[str] = mapped_column(String(255), primary_key=True)


class AgentPerformanceQueue(Base):
    __tablename__ = "agent_performance_queues"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "agent_email"], ["agents.tenant_id", "agents.agent_email"]
        ),
        ForeignKeyConstraint(["tenant_id", "queue"], ["queues.tenant_id", "queues.queue"]),
    )

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    agent_email: Mapped[str] = mapped_column(String(255), primary_key=True)
    queue: Mapped[str] = mapped_column(String(255), primary_key=True)


class AgentPerformance(Base):
    __tablename__ = "agent_performance"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "agent_email"], ["agents.tenant_id", "agents.agent_email"]
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    performance_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    agent_email: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str | None] = mapped_column(String(50))
    checkin: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    checkout: Mapped[datetime | None] = mapped_column(UTCTimestamp)


class AgentMetric(Base):
    __tablename__ = "agent_metrics"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "queue"], ["queues.tenant_id", "queues.queue"]),
        Index("ix_agent_metrics_tenant_creation", "tenant_id", "session_creation_time"),
        Index("ix_agent_metrics_tenant_chat", "tenant_id", "chat_id"),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.tenant_id"), primary_key=True
    )
    session_id: Mapped[str] = mapped_column(String(150), primary_key=True)
    chat_id: Mapped[str | None] = mapped_column(String(50))
    session_creation_time: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    avg_attending_time: Mapped[int | None] = mapped_column(Integer)
    avg_response_time: Mapped[int | None] = mapped_column(Integer)
    queue: Mapped[str | None] = mapped_column(String(255))
    agent_name: Mapped[str | None] = mapped_column(String(255))
    agent_id: Mapped[str | None] = mapped_column(String(50))
    typification: Mapped[str | None] = mapped_column(String(255))
    closed_time: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    open_sessions: Mapped[int | None] = mapped_column(Integer)
    closed_sessions: Mapped[int | None] = mapped_column(Integer)
    on_hold: Mapped[int | None] = mapped_column(Integer)
    op_response_time: Mapped[int | None] = mapped_column(Integer)
    operator_responses: Mapped[int | None] = mapped_column(Integer)
    session_transfer_in: Mapped[int | None] = mapped_column(Integer)
    session_transfer_out: Mapped[int | None] = mapped_column(Integer)
    session_transfer_out_no_messages: Mapped[int | None] = mapped_column(Integer)
    closed_with_no_messages: Mapped[int | None] = mapped_column(Integer)
    timeout_no_messages: Mapped[int | None] = mapped_column(Integer)
    agent_timeout: Mapped[int | None] = mapped_column(Integer)
    user_timeout: Mapped[int | None] = mapped_column(Integer)
    from_queue_asign_to_op_assigned: Mapped[int | None] = mapped_column(Integer)
    from_session_start_to_op_first_response: Mapped[int | None] = mapped_column(Integer)
    from_queue_asign_to_op_first_response: Mapped[int | None] = mapped_column(Integer)
    from_op_assigned_to_op_first_response: Mapped[int | None] = mapped_column(Integer)
    from_queue_asign_to_session_closed: Mapped[int | None] = mapped_column(Integer)
    from_op_assignation_to_session_closed: Mapped[int | None] = mapped_column(Integer)
    session_timeout: Mapped[int | None] = mapped_column(Integer)
    conversation_link: Mapped[str | None] = mapped_column(Text)


class Chat(Base):
    __tablename__ = "chats"

    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.tenant_id"), primary_key=True
    )
    chat_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    channel_id: Mapped[str | None] = mapped_column(String(255))
    contact_id: Mapped[str | None] = mapped_column(String(255))


class ChatDetail(Base):
    __tablename__ = "chat_details"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "chat_id"], ["chats.tenant_id", "chats.chat_id"]),
    )

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    creation_time: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    last_session_creation_time: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    external_id: Mapped[str | None] = mapped_column(String(100))
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(2))
    email: Mapped[str | None] = mapped_column(String(255))
    whatsapp_window_close_datetime: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    queue_id: Mapped[str | None] = mapped_column(String(255))
    agent_id: Mapped[str | None] = mapped_column(String(50))
    on_hold_agent_id: Mapped[str | None] = mapped_column(String(50))
    last_user_message_datetime: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    is_tester: Mapped[bool | None] = mapped_column(Boolean)
    is_bot_muted: Mapped[bool | None] = mapped_column(Boolean)
    is_banned: Mapped[bool | None] = mapped_column(Boolean)


class ChatVariable(Base):
    __tablename__ = "chat_variables"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "chat_id"], ["chats.tenant_id", "chats.chat_id"]),
    )

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    var_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    var_value: Mapped[str | None] = mapped_column(Text)


class ChatTag(Base):
    __tablename__ = "chat_tags"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "chat_id"], ["chats.tenant_id", "chats.chat_id"]),
    )

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tag: Mapped[str] = mapped_column(String(100), primary_key=True)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "chat_id"], ["chats.tenant_id", "chats.chat_id"]),
        ForeignKeyConstraint(["tenant_id", "queue_id"], ["queues.tenant_id", "queues.queue"]),
        Index("ix_messages_tenant_chat_time", "tenant_id", "chat_id", "creation_time"),
        Index("ix_messages_tenant_time", "tenant_id", "creation_time"),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.tenant_id"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    creation_time: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    message_from: Mapped[str | None] = mapped_column(String(50))  # 'user' | 'bot' | 'agent'…
    agent_id: Mapped[str | None] = mapped_column(String(50))
    queue_id: Mapped[str | None] = mapped_column(String(255))
    session_creation_time: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    chat_id: Mapped[str | None] = mapped_column(String(50))
    session_id: Mapped[str | None] = mapped_column(String(150))
    whatsapp_template_name: Mapped[str | None] = mapped_column(String(255))


class MessageContent(Base):
    __tablename__ = "message_content"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "message_id"], ["messages.tenant_id", "messages.id"]),
    )

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    content_type: Mapped[str | None] = mapped_column(String(50))  # 'type' en el legacy
    text: Mapped[str | None] = mapped_column(Text)
    selected_button: Mapped[str | None] = mapped_column(String(255))
    original_text: Mapped[str | None] = mapped_column(Text)
    original_audio_url: Mapped[str | None] = mapped_column(Text)


class MessageButton(Base):
    __tablename__ = "message_buttons"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "message_id"], ["messages.tenant_id", "messages.id"]),
    )

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    button: Mapped[str] = mapped_column(String(255), primary_key=True)


class MessageCarouselItem(Base):
    __tablename__ = "message_carouselitems"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "message_id"], ["messages.tenant_id", "messages.id"]),
    )

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    item_index: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    carousel_item: Mapped[str | None] = mapped_column(Text)


class MessageMedia(Base):
    __tablename__ = "message_media"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "message_id"], ["messages.tenant_id", "messages.id"]),
        Index("ix_message_media_tenant_message", "tenant_id", "message_id"),
    )

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    media_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(50), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)


class MessageLocation(Base):
    __tablename__ = "message_location"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "message_id"], ["messages.tenant_id", "messages.id"]),
    )

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    latitude: Mapped[str | None] = mapped_column(String(50))
    longitude: Mapped[str | None] = mapped_column(String(50))
    name: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)


class MessageCall(Base):
    __tablename__ = "message_call"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "message_id"], ["messages.tenant_id", "messages.id"]),
    )

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    event: Mapped[str | None] = mapped_column(String(50))


class EncryptionParams(Base):
    __tablename__ = "encryption_params"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "message_id"], ["messages.tenant_id", "messages.id"]),
    )

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    version: Mapped[str | None] = mapped_column(String(50))
    config_id: Mapped[str | None] = mapped_column(String(50))
    timestamp: Mapped[str | None] = mapped_column(String(50))
    encrypted_key: Mapped[str | None] = mapped_column(Text)


class MessageFile(Base):
    __tablename__ = "message_files"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "message_id"], ["messages.tenant_id", "messages.id"]),
        CheckConstraint(
            "status IN ('ok','forbidden','not_found','error','skipped')",
            name="ck_message_files_status",
        ),
        Index("ix_message_files_tenant_status_type", "tenant_id", "status", "file_type"),
    )

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    file_type: Mapped[str] = mapped_column(String(20), primary_key=True)  # 'media' | 'audio'
    original_url: Mapped[str] = mapped_column(String(500), nullable=False)
    s3_key: Mapped[str | None] = mapped_column(String(500))  # NULL si la descarga falló
    downloaded_at: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ok")
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    content_type: Mapped[str | None] = mapped_column(String(255))
