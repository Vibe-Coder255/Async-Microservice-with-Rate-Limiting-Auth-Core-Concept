# Async event ingest service

A high-throughput REST and WebSocket API for transactional event logging. It demonstrates production-style **async connection pooling**, **JWT + RBAC**, and an **atomic Redis Lua token bucket**, using only free local tools (FastAPI, PostgreSQL, Redis).

```
client (HTTP/WS)
       │
  [ FastAPI Async App ] ───(Lifespan: Async Pools)
       ├──> Token Bucket Limiter (Atomic Redis Lua Script)
       ├──> JWT Auth & RBAC Guard (OAuth2 + Scopes)
       ├──> Asyncpg / SQLAlchemy 2.0 Pool ──> PostgreSQL
       └──> WebSocket Event Broadcaster (Redis Pub/Sub)
```

## Quick start

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
docker compose up -d db redis
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

OpenAPI: [http://localhost:8000/docs](http://localhost:8000/docs)

Default seeded admin (local only): `admin@local.dev` / `adminadmin`

## API surface

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/health` | Liveness |
| `POST` | `/api/v1/auth/register` | Create user (`admin` only if none exists) |
| `POST` | `/api/v1/auth/login` | OAuth2 password → JWT |
| `GET` | `/api/v1/auth/me` | Current user |
| `POST` | `/api/v1/auth/api-keys` | Issue an API key (shown once) |
| `POST` | `/api/v1/events` | Single ingest (`ingest_writer`) |
| `POST` | `/api/v1/events/batch` | Bulk ingest, 1–1000 events |
| `GET` | `/api/v1/events` | Recent events (`viewer`) |
| `WS` | `/api/v1/events/stream?token=` | Redis Pub/Sub live feed |

Authenticate with `Authorization: Bearer <jwt>` or `X-API-Key: eik_...`.

Rate-limit headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`. Exceeding the bucket returns **429**.

## Tests and load

```powershell
pytest -q
locust -f locustfile.py --host http://localhost:8000
```

Optional: `k6 run loadtest/k6_events.js`

## Documentation

Step-by-step build notes:

1. [Local infrastructure](docs/01-local-infrastructure.md)
2. [Async database and Alembic](docs/02-async-database.md)
3. [JWT and RBAC](docs/03-jwt-rbac.md)
4. [Token-bucket limiter](docs/04-token-bucket.md)
5. [Ingest and WebSockets](docs/05-ingestion-websockets.md)
6. [Testing and load](docs/06-testing-observability.md)
7. [Implementation notes](docs/07-implementation-notes.md)
