from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import (
    CurrentUser,
    DbDep,
    ensure_tenant_exists,
    get_managed_tenant,
    require_admin,
    require_superadmin,
)
from app.core.crypto import encrypt_secret
from app.core.security import ROLE_SUPERADMIN, hash_password
from app.models import EtlRun, Tenant, TenantSettings, User
from app.schemas.admin import (
    EtlRunOut,
    TenantCreate,
    TenantOut,
    TenantSettingsOut,
    TenantSettingsUpdate,
    TenantUpdate,
    UserCreate,
    UserUpdate,
)
from app.schemas.auth import UserOut
from app.services.audit import audit

router = APIRouter(tags=["admin"])

SuperadminDep = Annotated[CurrentUser, Depends(require_superadmin)]
AdminDep = Annotated[CurrentUser, Depends(require_admin)]
ManagedTenantDep = Annotated[str, Depends(get_managed_tenant)]


# ——— Tenants (solo superadmin) ———

@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(_: SuperadminDep, db: DbDep):
    return (await db.scalars(select(Tenant).order_by(Tenant.tenant_id))).all()


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(body: TenantCreate, current: SuperadminDep, db: DbDep):
    if await db.get(Tenant, body.tenant_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "El tenant ya existe")
    tenant = Tenant(tenant_id=body.tenant_id, tenant_name=body.tenant_name)
    db.add(tenant)
    db.add(TenantSettings(tenant_id=body.tenant_id))
    await audit(db, action="tenant_created", tenant_id=body.tenant_id, user_id=current.id)
    await db.commit()
    return tenant


@router.patch("/tenants/{tenant_id}", response_model=TenantOut)
async def update_tenant(tenant_id: str, body: TenantUpdate, current: SuperadminDep, db: DbDep):
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant inexistente")
    if body.tenant_name is not None:
        tenant.tenant_name = body.tenant_name
    await audit(db, action="tenant_updated", tenant_id=tenant_id, user_id=current.id)
    await db.commit()
    return tenant


# ——— Settings del tenant ———

def _settings_out(s: TenantSettings) -> TenantSettingsOut:
    return TenantSettingsOut(
        tenant_id=s.tenant_id,
        botmaker_client_id=s.botmaker_client_id,
        has_botmaker_credentials=bool(s.botmaker_token_enc),
        etl_schedule_cron=s.etl_schedule_cron,
        etl_initial_ts=s.etl_initial_ts,
        etl_window_days=s.etl_window_days,
        is_etl_enabled=s.is_etl_enabled,
        logo_url=s.logo_url,
        siniestros_queue=s.siniestros_queue,
        siniestros_button=s.siniestros_button,
    )


@router.get("/tenants/{tenant_id}/settings", response_model=TenantSettingsOut)
async def get_tenant_settings(tenant_id: str, _: SuperadminDep, db: DbDep):
    settings = await db.get(TenantSettings, tenant_id)
    if settings is None:
        await ensure_tenant_exists(db, tenant_id)
        settings = TenantSettings(tenant_id=tenant_id)
        db.add(settings)
        await db.commit()
    return _settings_out(settings)


@router.put("/tenants/{tenant_id}/settings", response_model=TenantSettingsOut)
async def update_tenant_settings(
    tenant_id: str, body: TenantSettingsUpdate, current: SuperadminDep, db: DbDep
):
    await ensure_tenant_exists(db, tenant_id)
    settings = await db.get(TenantSettings, tenant_id)
    if settings is None:
        settings = TenantSettings(tenant_id=tenant_id)
        db.add(settings)

    # Credenciales: write-only, cifradas at-rest (§8.2)
    if body.botmaker_client_id is not None:
        settings.botmaker_client_id = body.botmaker_client_id
    if body.botmaker_secret_id is not None:
        settings.botmaker_secret_id = body.botmaker_secret_id
    if body.botmaker_token is not None:
        settings.botmaker_token_enc = encrypt_secret(body.botmaker_token)
    if body.botmaker_refresh_token is not None:
        settings.botmaker_refresh_token_enc = encrypt_secret(body.botmaker_refresh_token)

    for field in (
        "etl_schedule_cron", "etl_initial_ts", "etl_window_days",
        "is_etl_enabled", "logo_url", "siniestros_queue", "siniestros_button",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(settings, field, value)

    await audit(
        db, action="tenant_settings_updated", tenant_id=tenant_id, user_id=current.id,
        detail={"credentials_changed": body.botmaker_token is not None},
    )
    await db.commit()
    return _settings_out(settings)


# ——— Usuarios ———

@router.get("/users", response_model=list[UserOut])
async def list_users(current: AdminDep, db: DbDep, tenant_scope: ManagedTenantDep):
    return (
        await db.scalars(
            select(User).where(User.tenant_id == tenant_scope).order_by(User.email)
        )
    ).all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, current: AdminDep, db: DbDep):
    if body.role == ROLE_SUPERADMIN:
        if not current.is_superadmin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo superadmin crea superadmins")
        tenant_id = None
    else:
        # tenant_admin solo crea usuarios en su propio tenant
        tenant_id = body.tenant_id if current.is_superadmin else current.tenant_id
        if not tenant_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "tenant_id requerido")
        if not current.is_superadmin and body.tenant_id not in (None, current.tenant_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No puede crear usuarios de otro tenant")
        await ensure_tenant_exists(db, tenant_id)

    email = body.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "El email ya está registrado")

    user = User(
        tenant_id=tenant_id, email=email, password_hash=hash_password(body.password),
        full_name=body.full_name, role=body.role, is_active=True,
    )
    db.add(user)
    await audit(db, action="user_created", tenant_id=tenant_id, user_id=current.id,
                entity="user", entity_id=email)
    await db.commit()
    await db.refresh(user)
    return user


async def _get_managed_user(user_id: int, current: CurrentUser, db) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario inexistente")
    if not current.is_superadmin and user.tenant_id != current.tenant_id:
        # No revelar existencia de usuarios de otros tenants
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario inexistente")
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: int, body: UserUpdate, current: AdminDep, db: DbDep):
    user = await _get_managed_user(user_id, current, db)
    if user.role == ROLE_SUPERADMIN and not current.is_superadmin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permisos insuficientes")
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.role is not None and user.role != ROLE_SUPERADMIN:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    await audit(db, action="user_updated", tenant_id=user.tenant_id, user_id=current.id,
                entity="user", entity_id=user.email)
    await db.commit()
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(user_id: int, current: AdminDep, db: DbDep):
    """Baja lógica (is_active=false); no se borran filas por auditoría."""
    user = await _get_managed_user(user_id, current, db)
    if user.id == current.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puede darse de baja a sí mismo")
    user.is_active = False
    await audit(db, action="user_deactivated", tenant_id=user.tenant_id, user_id=current.id,
                entity="user", entity_id=user.email)
    await db.commit()


# ——— Monitoreo ETL ———

@router.get("/etl/runs")
async def list_etl_runs(
    current: AdminDep,
    db: DbDep,
    tenant_scope: ManagedTenantDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    base = select(EtlRun).where(EtlRun.tenant_id == tenant_scope)
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    runs = (
        await db.scalars(
            base.order_by(EtlRun.started_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [EtlRunOut.model_validate(r) for r in runs],
    }
