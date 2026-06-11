import time
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()

ROLE_SUPERADMIN = "superadmin"
ROLE_TENANT_ADMIN = "tenant_admin"
ROLE_VIEWER = "viewer"
ROLES = {ROLE_SUPERADMIN, ROLE_TENANT_ADMIN, ROLE_VIEWER}


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def create_token(user_id: int, tenant_id: str | None, role: str, token_type: str, ttl: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "tenant_id": tenant_id,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def create_access_token(user_id: int, tenant_id: str | None, role: str) -> str:
    return create_token(user_id, tenant_id, role, "access", get_settings().jwt_access_ttl)


def create_refresh_token(user_id: int, tenant_id: str | None, role: str) -> str:
    return create_token(user_id, tenant_id, role, "refresh", get_settings().jwt_refresh_ttl)


def decode_token(token: str, expected_type: str = "access") -> dict:
    """Decodifica y valida el JWT. Lanza jwt.InvalidTokenError si es inválido."""
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"se esperaba token de tipo {expected_type}")
    return payload


class LoginRateLimiter:
    """Rate-limit en memoria por clave (ip+email) con ventana deslizante simple.

    Suficiente para un deploy de proceso único (v1); con múltiples réplicas
    migrar a un contador en DB o Redis.
    """

    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}

    def is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        attempts = [t for t in self._attempts.get(key, []) if now - t < self.window_seconds]
        self._attempts[key] = attempts
        return len(attempts) >= self.max_attempts

    def register_failure(self, key: str) -> None:
        self._attempts.setdefault(key, []).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._attempts.pop(key, None)


login_rate_limiter = LoginRateLimiter(
    max_attempts=get_settings().login_max_attempts,
    window_seconds=get_settings().login_lockout_minutes * 60,
)
