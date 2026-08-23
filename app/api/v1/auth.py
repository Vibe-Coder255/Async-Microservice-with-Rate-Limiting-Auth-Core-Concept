from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_current_principal, require_scopes
from app.core.database import get_db
from app.core.security import (
    ROLE_SCOPES,
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.api_key import APIKey
from app.models.user import User, UserRole
from app.schemas.auth import (
    APIKeyCreate,
    APIKeyCreated,
    APIKeyRead,
    Token,
    UserCreate,
    UserRead,
)
from app.services.rate_limiter import generate_api_key, hash_api_key

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, session: AsyncSession = Depends(get_db)) -> User:
    existing = await session.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=UserRole.VIEWER,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_db),
) -> Token:
    result = await session.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    token = create_access_token(subject=str(user.id), role=user.role.value)
    return Token(access_token=token, role=user.role, scopes=ROLE_SCOPES[user.role.value])


@router.get("/me", response_model=UserRead)
async def me(principal: Principal = Depends(get_current_principal)) -> User:
    return principal.user


@router.post("/api-keys", response_model=APIKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: APIKeyCreate,
    session: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_scopes("ingest_writer")),
) -> APIKeyCreated:
    raw_key = generate_api_key()
    record = APIKey(
        name=payload.name,
        key_hash=hash_api_key(raw_key),
        user_id=principal.user.id,
        rate_limit_tier=payload.rate_limit_tier,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return APIKeyCreated(
        id=record.id,
        name=record.name,
        rate_limit_tier=record.rate_limit_tier,
        api_key=raw_key,
    )


@router.get("/api-keys", response_model=list[APIKeyRead])
async def list_api_keys(
    session: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[APIKey]:
    stmt = select(APIKey).where(APIKey.user_id == principal.user.id)
    if principal.user.role == UserRole.ADMIN:
        stmt = select(APIKey)
    result = await session.execute(stmt)
    return list(result.scalars().all())
