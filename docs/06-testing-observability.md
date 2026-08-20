# Step 6 — Tests, load, and local observability

All tooling here is free and local: **pytest-asyncio**, **httpx**, **Locust**, and optional **k6**.

## Unit tests (no Docker)

```powershell
pytest tests/test_security.py -q
```

Covers bcrypt round-trip, JWT claims/scopes, and API-key hashing.

## Integration tests (Postgres + Redis)

```powershell
docker compose up -d db redis
alembic upgrade head
pytest tests/test_api.py -q
```

If either dependency is down, those tests **skip** instead of erroring. They cover:

- `/health`
- JWT login + single ingest + rate-limit headers
- Batch ingest
- Viewer forbidden on write
- Free-tier API key eventually receiving **HTTP 429**

## Locust (HTTP load)

With the API running:

```powershell
locust -f locustfile.py --host http://localhost:8000 --users 200 --spawn-rate 50
```

Open `http://localhost:8089` for the UI, or add `--headless -t 2m`. 429s are treated as expected limiter behavior, not failures.

To push toward 1,000 concurrent users locally:

```powershell
locust -f locustfile.py --host http://localhost:8000 --headless --users 1000 --spawn-rate 100 -t 3m
```

Watch Postgres (`asyncpg` pool of 20+10) and Redis CPU. Pool exhaustion shows up as rising wait time, not SQL deadlocks — this schema has no contended row-level locks on ingest.

## k6 (optional)

If you install [k6](https://k6.io) locally:

```powershell
k6 run loadtest/k6_events.js
```

Thresholds in the script flag high error rates and a 95th percentile above 50 ms. Sub-10 ms single-write latency is typical on a warm local pool; first requests include TLS-less TCP + auth + insert.

## What “healthy under load” looks like

- No `QueuePool` timeout traces in Uvicorn logs
- Mix of `200` and `429` for free-tier keys; premium/admin mostly `200`
- Redis `INFO stats` showing `instantaneous_ops_per_sec` climbing without script errors
- WebSocket clients continuing to receive JSON while ingest is under load
