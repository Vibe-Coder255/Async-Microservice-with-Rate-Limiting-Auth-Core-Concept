# Step 1 — Local infrastructure and environment

This service is designed to run fully offline on a laptop: **Docker** for PostgreSQL 16 and Redis 7, **Python 3.12** for the API, and no commercial cloud APIs.

## What you are standing up

| Component | Role | Default local endpoint |
| --- | --- | --- |
| PostgreSQL 16 | Durable event, user, and API-key storage | `localhost:5432` |
| Redis 7 | Atomic token-bucket limiter + Pub/Sub fan-out | `localhost:6379` |
| FastAPI app | Async HTTP + WebSocket surface | `localhost:8000` |

Compose health checks keep the API from starting until Postgres accepts connections (`pg_isready`) and Redis answers `PING`.

## Commands

From the repository root:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
docker compose up -d db redis
```

Wait until both containers are healthy, then apply the schema (step 2) and start Uvicorn:

```powershell
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

To run API + database + Redis together:

```powershell
docker compose up --build
```

Inside Compose, `DATABASE_URL` points at host `db` and `REDIS_URL` at host `redis`. On the host machine those same services are `localhost`.

## Typed settings

`app/core/config.py` loads `.env` with **pydantic-settings**. Important variables:

- `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/event_db`
- `REDIS_URL=redis://localhost:6379/0`
- `SECRET_KEY` — HMAC key for JWTs (replace for anything beyond local learning)
- `POOL_SIZE` / `MAX_OVERFLOW` — SQLAlchemy pool (20 / 10 by default)
- `SEED_ADMIN` — creates `admin@local.dev` / `adminadmin` on first boot

`get_settings()` is cached so tests can call `get_settings.cache_clear()` after mutating environment variables.
