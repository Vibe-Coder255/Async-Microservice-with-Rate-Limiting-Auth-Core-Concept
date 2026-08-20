from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import SessionLocal, dispose_engine, init_engine
from app.core.redis import close_redis, init_redis
from app.core.security import hash_password
from app.models import APIKey, EventLog  # noqa: F401
from app.models.user import User, UserRole
from app.services.rate_limiter import TokenBucketLimiter


async def _seed_admin() -> None:
    if not settings.seed_admin or SessionLocal is None:
        return
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.email == settings.seed_admin_email))
        if result.scalar_one_or_none() is not None:
            return
        session.add(
            User(
                email=settings.seed_admin_email,
                hashed_password=hash_password(settings.seed_admin_password),
                role=UserRole.ADMIN,
            )
        )
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine()
    redis = await init_redis()
    limiter = TokenBucketLimiter(redis)
    await limiter.load_script()
    app.state.limiter = limiter
    await _seed_admin()
    yield
    await close_redis()
    await dispose_engine()


app = FastAPI(
    title=settings.project_name,
    lifespan=lifespan,
    description=(
        "Async event ingestion service with JWT/RBAC, atomic Redis token-bucket "
        "rate limiting, and Redis Pub/Sub WebSocket fan-out."
    ),
)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
