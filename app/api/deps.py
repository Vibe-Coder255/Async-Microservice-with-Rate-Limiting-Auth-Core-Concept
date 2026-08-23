import time
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ROLE_SCOPES, ROLE_TIER, decode_token
from app.models.api_key import APIKey
from app.models.user import User, UserRole
from app.services.rate_limiter import TokenBucketLimiter, hash_api_key, tier_params

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)


@dataclass
class Principal:
    user: User
    api_key: APIKey | None
    scopes: list[str]
    rate_limit_key: str
    rate_limit_tier: str


async def _user_from_api_key(session: AsyncSession, raw_key: str) -> Principal:
    key_hash = hash_api_key(raw_key)
    result = await session.execute(
        select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True))
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    user_result = await session.execute(select(User).where(User.id == api_key.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    return Principal(
        user=user,
        api_key=api_key,
        scopes=ROLE_SCOPES[user.role.value],
        rate_limit_key=f"rl:apikey:{api_key.id}",
        rate_limit_tier=api_key.rate_limit_tier,
    )


async def _user_from_bearer(session: AsyncSession, token: str) -> Principal:
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await session.execute(select(User).where(User.id == UUID(subject)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    scopes = ROLE_SCOPES[user.role.value]
    return Principal(
        user=user,
        api_key=None,
        scopes=list(scopes),
        rate_limit_key=f"rl:user:{user.id}",
        rate_limit_tier=ROLE_TIER[user.role.value],
    )


async def get_current_principal(
    session: AsyncSession = Depends(get_db),
    token: str | None = Depends(oauth2_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Principal:
    if x_api_key:
        return await _user_from_api_key(session, x_api_key)
    if token:
        return await _user_from_bearer(session, token)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(principal: Principal = Depends(get_current_principal)) -> User:
    return principal.user


def require_scopes(*required: str):
    async def checker(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.user.role == UserRole.ADMIN:
            return principal
        missing = [scope for scope in required if scope not in principal.scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing scopes: {', '.join(missing)}",
            )
        return principal

    return checker


async def consume_rate_limit(
    request: Request,
    response: Response,
    principal: Principal,
    cost: int,
) -> Principal:
    if cost < 1:
        cost = 1
    limiter: TokenBucketLimiter = request.app.state.limiter
    params = tier_params(principal.rate_limit_tier)
    capacity = params["capacity"]
    if cost > capacity:
        reset_epoch = int(time.time() + max(1, (cost - capacity) / max(params["refill_rate"], 0.0001)))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Batch size {cost} exceeds tier capacity of {int(capacity)}",
            headers={
                "Retry-After": str(max(1, reset_epoch - int(time.time()))),
                "X-RateLimit-Limit": str(int(capacity)),
                "X-RateLimit-Remaining": str(0),
                "X-RateLimit-Reset": str(reset_epoch),
            },
        )
    allowed, remaining, reset_epoch = await limiter.consume(
        key=principal.rate_limit_key,
        capacity=capacity,
        refill_rate=params["refill_rate"],
        cost=cost,
    )
    response.headers["X-RateLimit-Limit"] = str(int(capacity))
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset_epoch)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(max(1, reset_epoch - int(time.time()))),
                "X-RateLimit-Limit": str(int(capacity)),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(reset_epoch),
            },
        )
    return principal


class RateLimiter:
    """FastAPI dependency that consumes tokens from the Redis token bucket."""

    def __init__(self, cost: int = 1):
        self.cost = cost

    async def __call__(
        self,
        request: Request,
        response: Response,
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        return await consume_rate_limit(request, response, principal, self.cost)
