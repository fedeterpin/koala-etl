from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class TenantCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    tenant_name: str = Field(min_length=1, max_length=255)


class TenantUpdate(BaseModel):
    tenant_name: str | None = None


class TenantOut(BaseModel):
    tenant_id: str
    tenant_name: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class TenantSettingsUpdate(BaseModel):
    """Credenciales Botmaker write-only: se aceptan acá pero nunca se devuelven."""

    botmaker_client_id: str | None = None
    botmaker_secret_id: str | None = None
    botmaker_token: str | None = None
    botmaker_refresh_token: str | None = None
    etl_schedule_cron: str | None = None
    etl_initial_ts: datetime | None = None
    etl_window_days: int | None = Field(default=None, ge=1, le=31)
    is_etl_enabled: bool | None = None
    logo_url: str | None = None
    siniestros_queue: str | None = None
    siniestros_button: str | None = None


class TenantSettingsOut(BaseModel):
    tenant_id: str
    botmaker_client_id: str | None = None
    has_botmaker_credentials: bool = False
    etl_schedule_cron: str | None = None
    etl_initial_ts: datetime | None = None
    etl_window_days: int | None = None
    is_etl_enabled: bool = False
    logo_url: str | None = None
    siniestros_queue: str | None = None
    siniestros_button: str | None = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)
    role: str = Field(pattern=r"^(superadmin|tenant_admin|viewer)$")
    tenant_id: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = Field(default=None, min_length=8)
    role: str | None = Field(default=None, pattern=r"^(tenant_admin|viewer)$")
    is_active: bool | None = None


class EtlRunOut(BaseModel):
    id: int
    tenant_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    stats: dict[str, Any] | None
    error_summary: str | None

    model_config = {"from_attributes": True}


class Page(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]
