# Step 7 — Implementation notes (offline / free stack)

This project is intentionally self-contained:

| Need | Choice | Why |
| --- | --- | --- |
| HTTP + WS | FastAPI + Uvicorn | Native async, OpenAPI, WebSockets |
| Database | PostgreSQL 16 via asyncpg | JSONB, UUIDs, proven pooling |
| ORM / migrations | SQLAlchemy 2.0 + Alembic asyncio | Typed mappings, offline-friendly |
| Rate limit + fan-out | Redis 7 + Lua + Pub/Sub | Atomic limiter without a cloud API gateway |
| Auth | passlib/bcrypt + python-jose | Standard JWT/RBAC, no IdP required |
| Tests | pytest-asyncio + httpx | In-process ASGI tests |
| Load | Locust (Python) / k6 | Both run against localhost |

## Request path (happy path)

1. Lifespan opens the asyncpg pool, Redis client, and loads the Lua SHA.
2. Client authenticates (JWT or API key).
3. `RateLimiter` `EVALSHA`s the token bucket.
4. Handler bulk-inserts `event_logs`.
5. Pipeline `PUBLISH`es to `events:stream`.
6. Connected WebSocket subscribers receive the JSON.

## Layout (repository root)

The blueprint’s `event-ingest-service/` tree is this repository’s root (`app/`, `migrations/`, `tests/`, `docs/`).

## Local-only defaults to change later

- `SECRET_KEY` and seed admin password in `.env`
- Compose Postgres password
- Rate-limit tier table in `Settings.rate_limit_tiers`

No cloud object storage, managed queues, or paid observability backends are required to develop, test, or load-test this service.
