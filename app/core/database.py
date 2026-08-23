from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


def init_engine() -> AsyncEngine:
    global engine, SessionLocal
    engine = create_async_engine(
        settings.database_url,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
    )
    SessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return engine


async def dispose_engine() -> None:
    global engine, SessionLocal
    if engine is not None:
        await engine.dispose()
    engine = None
    SessionLocal = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if SessionLocal is None:
        raise RuntimeError("Database engine is not initialized")
    async with SessionLocal() as session:
        yield session


def get_db_context() -> AsyncSession:
    if SessionLocal is None:
        raise RuntimeError("Database engine is not initialized")
    return SessionLocal()
