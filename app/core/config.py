from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_name: str = "event-ingest-service"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/event_db"
    pool_size: int = 20
    max_overflow: int = 10

    redis_url: str = "redis://localhost:6379/0"
    redis_events_channel: str = "events:stream"

    secret_key: str = "change-me-to-a-long-random-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    seed_admin: bool | None = None
    seed_admin_email: str = "admin@local.dev"
    seed_admin_password: str = "adminadmin"

    rate_limit_tiers: dict[str, dict[str, float]] = Field(
        default_factory=lambda: {
            "free": {"capacity": 10, "refill_rate": 1.0},
            "standard": {"capacity": 100, "refill_rate": 10.0},
            "premium": {"capacity": 1000, "refill_rate": 100.0},
        }
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
