from datetime import datetime

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    tenant_id: str | None
    is_active: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class MeOut(UserOut):
    tenant_name: str | None = None
    logo_url: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut
