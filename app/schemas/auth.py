from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    role: UserRole = UserRole.VIEWER


class UserRead(BaseModel):
    id: UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    scopes: list[str]


class APIKeyCreate(BaseModel):
    name: str = Field(default="default", max_length=128)
    rate_limit_tier: str = Field(default="free", pattern="^(free|standard|premium)$")


class APIKeyCreated(BaseModel):
    id: UUID
    name: str
    rate_limit_tier: str
    api_key: str
    warning: str = "Store this key now. It is not shown again."


class APIKeyRead(BaseModel):
    id: UUID
    name: str
    rate_limit_tier: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
