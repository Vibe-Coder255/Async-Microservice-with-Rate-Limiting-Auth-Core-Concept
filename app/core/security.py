from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.models.user import UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ROLE_SCOPES: dict[str, list[str]] = {
    UserRole.ADMIN.value: ["admin", "ingest_writer", "viewer"],
    UserRole.INGEST_WRITER.value: ["ingest_writer", "viewer"],
    UserRole.VIEWER.value: ["viewer"],
}

ROLE_TIER: dict[str, str] = {
    UserRole.ADMIN.value: "premium",
    UserRole.INGEST_WRITER.value: "standard",
    UserRole.VIEWER.value: "free",
}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: str,
    role: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "scopes": ROLE_SCOPES.get(role, ["viewer"]),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
