# Step 2 — Async database layer and migrations

## Engine and session factory

`app/core/database.py` creates a SQLAlchemy 2.0 **async** engine with the `asyncpg` driver:

- `pool_size=20`
- `max_overflow=10`
- `pool_pre_ping=True` so stale connections are discarded
- `pool_recycle=1800` so long-lived connections are recycled

The engine is created in the FastAPI **lifespan** hook, not at import time. That avoids connecting during test collection and makes shutdown (`engine.dispose()`) deterministic.

`get_db()` yields an `AsyncSession` per request and closes it when the request finishes.

## Mapped models

UUID primary keys and JSONB payloads (PostgreSQL-native types):

| Table | Purpose |
| --- | --- |
| `users` | Email, bcrypt hash, role (`admin`, `ingest_writer`, `viewer`) |
| `api_keys` | SHA-256 of the raw key, owning user, `rate_limit_tier` |
| `event_logs` | Ingested events: `event_type` + JSONB `payload` |

Models live under `app/models/` and share `Base` so Alembic can discover metadata.

## Alembic with asyncio

`migrations/env.py` uses `async_engine_from_config` and:

```python
asyncio.run(run_async_migrations())
```

The connection is borrowed with `connection.run_sync(do_run_migrations)` because Alembic’s migration context is synchronous.

Baseline revision: `migrations/versions/0001_initial.py`.

```powershell
alembic upgrade head
alembic current
```

Bulk writes use `session.execute(insert(EventLog), [...])` instead of ORM `add()` loops so a 1–1000 event batch is one prepared statement plus one commit.
