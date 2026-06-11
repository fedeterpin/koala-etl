"""Dependencias de FastAPI: usuario actual, scoping de tenant y roles.

Regla de seguridad central (§8.1): el tenant se resuelve SIEMPRE desde el JWT.
El único caso en que se acepta `?tenant_id=` es un superadmin explícito.
"""

from dataclasses import dataclass
from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ROLE_SUPERADMIN, ROLE_TENANT_ADMIN, decode_token
from app.db.base import get_db
from app.models import User


@dataclass
class CurrentUser:
    user: User

    @property
    def id(self) -> int:
        return self.user.id

    @property
    def role(self) -> str:
        return self.user.role

    @property
    def tenant_id(self) -> str | None:
        return self.user.tenant_id

    @property
    def is_superadmin(self) -> bool:
        return self.user.role == ROLE_SUPERADMIN


def _bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token requerido")
    return auth.removeprefix("Bearer ").strip()


async def get_current_user(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> CurrentUser:
    token = _bearer_token(request)
    try:
        payload = decode_token(token, expected_type="access")
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o expirado") from e

    user = await db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario inactivo o inexistente")
    return CurrentUser(user=user)


def require_roles(*roles: str):
    async def checker(current: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if current.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permisos insuficientes")
        return current

    return checker


require_admin = require_roles(ROLE_SUPERADMIN, ROLE_TENANT_ADMIN)
require_superadmin = require_roles(ROLE_SUPERADMIN)


async def get_tenant_scope(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    tenant_id: Annotated[str | None, Query()] = None,
) -> str:
    """Tenant efectivo para queries scoped.

    - Usuario de tenant: SIEMPRE su tenant del token; si pasa otro tenant_id → 403.
    - Superadmin: debe indicar ?tenant_id= explícito.
    """
    if current.is_superadmin:
        if not tenant_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "superadmin debe indicar ?tenant_id="
            )
        return tenant_id
    if tenant_id is not None and tenant_id != current.tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puede acceder a otro tenant")
    assert current.tenant_id is not None
    return current.tenant_id


async def get_managed_tenant(
    current: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[str | None, Query()] = None,
) -> str:
    """Tenant que un admin puede administrar (usuarios, reintentos, backups)."""
    scope = await get_tenant_scope(current, tenant_id)
    if current.role == ROLE_TENANT_ADMIN and scope != current.tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puede administrar otro tenant")
    return scope


DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
TenantScopeDep = Annotated[str, Depends(get_tenant_scope)]


async def ensure_tenant_exists(db: AsyncSession, tenant_id: str) -> None:
    from app.models import Tenant

    exists = await db.scalar(select(Tenant.tenant_id).where(Tenant.tenant_id == tenant_id))
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant inexistente")
