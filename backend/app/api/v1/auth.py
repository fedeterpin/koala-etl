from datetime import UTC, datetime

import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    login_rate_limiter,
    verify_password,
)
from app.models import Tenant, TenantSettings, User
from app.schemas.auth import LoginRequest, MeOut, RefreshRequest, TokenPair, UserOut
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_pair(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id, user.tenant_id, user.role),
        refresh_token=create_refresh_token(user.id, user.tenant_id, user.role),
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, request: Request, db: DbDep) -> TokenPair:
    client_ip = request.client.host if request.client else "?"
    rate_key = f"{client_ip}:{body.email.lower()}"
    if login_rate_limiter.is_blocked(rate_key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Demasiados intentos fallidos; intente más tarde",
        )

    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        login_rate_limiter.register_failure(rate_key)
        await audit(
            db, action="login_failed",
            tenant_id=user.tenant_id if user else None,
            user_id=user.id if user else None,
            detail={"email": body.email.lower(), "ip": client_ip},
        )
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")

    login_rate_limiter.reset(rate_key)
    user.last_login_at = datetime.now(UTC)
    await audit(
        db, action="login_ok", tenant_id=user.tenant_id, user_id=user.id,
        detail={"ip": client_ip},
    )
    await db.commit()
    return _token_pair(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, db: DbDep) -> TokenPair:
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token inválido") from e

    user = await db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario inactivo o inexistente")
    return _token_pair(user)


@router.get("/me", response_model=MeOut)
async def me(current: CurrentUserDep, db: DbDep) -> MeOut:
    out = MeOut.model_validate(current.user)
    if current.tenant_id:
        tenant = await db.get(Tenant, current.tenant_id)
        settings = await db.get(TenantSettings, current.tenant_id)
        out.tenant_name = tenant.tenant_name if tenant else None
        out.logo_url = settings.logo_url if settings else None
    return out
