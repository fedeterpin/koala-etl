"""Tablas nuevas de la plataforma SaaS (PLAN-APP.md §5.2)."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

UTCTimestamp = TIMESTAMP(timezone=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('superadmin','tenant_admin','viewer')", name="ck_users_role"
        ),
        # superadmin no tiene tenant; los demás roles sí
        CheckConstraint(
            "(role = 'superadmin' AND tenant_id IS NULL) OR (role <> 'superadmin' AND tenant_id IS NOT NULL)",
            name="ck_users_tenant_by_role",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("tenants.tenant_id"))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        UTCTimestamp, nullable=False, server_default=text("now()")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(UTCTimestamp)


class TenantSettings(Base):
    __tablename__ = "tenant_settings"

    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.tenant_id"), primary_key=True
    )
    botmaker_client_id: Mapped[str | None] = mapped_column(String(255))
    botmaker_secret_id: Mapped[str | None] = mapped_column(String(255))
    botmaker_token_enc: Mapped[str | None] = mapped_column(Text)
    botmaker_refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    etl_schedule_cron: Mapped[str | None] = mapped_column(String(100))  # ej: "0 3 * * *"
    etl_initial_ts: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    etl_window_days: Mapped[int | None] = mapped_column(Integer)
    is_etl_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    logo_url: Mapped[str | None] = mapped_column(Text)
    # Condición "es siniestro" configurable por tenant (§7.1 página Siniestros)
    siniestros_queue: Mapped[str | None] = mapped_column(String(255))
    siniestros_button: Mapped[str | None] = mapped_column(String(255))


class EtlControl(Base):
    """Ventana deslizante por (tenant, endpoint). El legacy era global; ahora por tenant."""

    __tablename__ = "etl_control"

    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.tenant_id"), primary_key=True
    )
    endpoint: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_ts: Mapped[datetime | None] = mapped_column(UTCTimestamp)


class EtlRun(Base):
    __tablename__ = "etl_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','ok','partial','failed')", name="ck_etl_runs_status"
        ),
        Index("ix_etl_runs_tenant_started", "tenant_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.tenant_id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        UTCTimestamp, nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="running")
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_summary: Mapped[str | None] = mapped_column(Text)


class EtlStageError(Base):
    __tablename__ = "etl_stage_errors"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("etl_runs.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        UTCTimestamp, nullable=False, server_default=text("now()")
    )


class BackupJob(Base):
    __tablename__ = "backup_jobs"
    __table_args__ = (
        CheckConstraint("type IN ('full','incremental')", name="ck_backup_jobs_type"),
        CheckConstraint(
            "status IN ('pending','running','done','failed')", name="ck_backup_jobs_status"
        ),
        Index("ix_backup_jobs_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.tenant_id"), nullable=False
    )
    requested_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="full")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    s3_key_result: Mapped[str | None] = mapped_column(String(500))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        UTCTimestamp, nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    expires_at: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    error_summary: Mapped[str | None] = mapped_column(Text)


class RetryJob(Base):
    """Job de reintento de descargas fallidas encolado desde la API (§7.3)."""

    __tablename__ = "retry_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','done','failed')", name="ck_retry_jobs_status"
        ),
        Index("ix_retry_jobs_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.tenant_id"), nullable=False
    )
    requested_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    filters: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # statuses, file_types, ids, limit
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    counts_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    counts_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    processed: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        UTCTimestamp, nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(UTCTimestamp)
    error_summary: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(50))
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(255))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        UTCTimestamp, nullable=False, server_default=text("now()")
    )
