import os

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

os.environ.setdefault("SEED_ADMIN", "true")
os.environ.setdefault("SEED_ADMIN_EMAIL", "admin@local.dev")
os.environ.setdefault("SEED_ADMIN_PASSWORD", "adminadmin")

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()


async def _infra_available() -> bool:
    settings = get_settings()
    try:
        engine = create_async_engine(settings.database_url, pool_size=1, max_overflow=0)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        redis = Redis.from_url(settings.redis_url)
        await redis.ping()
        await redis.aclose()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="session")
async def require_infra():
    if not await _infra_available():
        pytest.skip("PostgreSQL and Redis must be running for integration tests")


@pytest.fixture
async def client(require_infra):
    from app.main import app

    transport = ASGITransport(app=app, lifespan="on")
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_health(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_login_and_ingest_single_event(client: AsyncClient):
    token = await _login(client, "admin@local.dev", "adminadmin")
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.post(
        "/api/v1/events",
        headers=headers,
        json={"event_type": "page.view", "payload": {"path": "/pricing"}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["event_type"] == "page.view"
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers


async def test_batch_ingest(client: AsyncClient):
    token = await _login(client, "admin@local.dev", "adminadmin")
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.post(
        "/api/v1/events/batch",
        headers=headers,
        json={
            "events": [
                {"event_type": "order.created", "payload": {"id": 1}},
                {"event_type": "order.paid", "payload": {"id": 1}},
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] == 2
    assert len(body["event_ids"]) == 2


async def test_viewer_cannot_ingest(client: AsyncClient):
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": "viewer@local.dev", "password": "viewerpass"},
    )
    assert register.status_code in {201, 409}
    token = await _login(client, "viewer@local.dev", "viewerpass")
    response = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={"event_type": "blocked", "payload": {}},
    )
    assert response.status_code == 403


async def test_rate_limit_returns_429(client: AsyncClient):
    token = await _login(client, "admin@local.dev", "adminadmin")
    headers = {"Authorization": f"Bearer {token}"}
    keys = await client.post(
        "/api/v1/auth/api-keys",
        headers=headers,
        json={"name": "load", "rate_limit_tier": "free"},
    )
    assert keys.status_code == 201, keys.text
    api_key = keys.json()["api_key"]
    api_headers = {"X-API-Key": api_key}

    statuses = []
    for i in range(12):
        response = await client.post(
            "/api/v1/events",
            headers=api_headers,
            json={"event_type": "burst", "payload": {"n": i}},
        )
        statuses.append(response.status_code)
        if response.status_code == 429:
            assert "X-RateLimit-Remaining" in response.headers
            break
    assert 429 in statuses


async def test_admin_can_create_premium_api_key(client: AsyncClient):
    token = await _login(client, "admin@local.dev", "adminadmin")
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.post(
        "/api/v1/auth/api-keys",
        headers=headers,
        json={"name": "premium-key", "rate_limit_tier": "premium"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["rate_limit_tier"] == "premium"
    assert "api_key" in body


async def test_viewer_cannot_create_api_keys(client: AsyncClient):
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": "viewer_nokey@local.dev", "password": "viewerpass"},
    )
    assert register.status_code in {201, 409}
    token = await _login(client, "viewer_nokey@local.dev", "viewerpass")
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.post(
        "/api/v1/auth/api-keys",
        headers=headers,
        json={"name": "blocked", "rate_limit_tier": "free"},
    )
    assert response.status_code == 403


def _make_batch_events(count: int) -> list[dict]:
    return [
        {"event_type": "batch.item", "payload": {"i": i}}
        for i in range(count)
    ]


async def test_batch_charges_tokens_proportional_to_size(client: AsyncClient):
    token = await _login(client, "admin@local.dev", "adminadmin")
    headers = {"Authorization": f"Bearer {token}"}
    keys = await client.post(
        "/api/v1/auth/api-keys",
        headers=headers,
        json={"name": "batch-proportional", "rate_limit_tier": "free"},
    )
    assert keys.status_code == 201, keys.text
    api_key = keys.json()["api_key"]
    api_headers = {"X-API-Key": api_key}

    size = 5
    response = await client.post(
        "/api/v1/events/batch",
        headers=api_headers,
        json={"events": _make_batch_events(size)},
    )
    assert response.status_code == 200, response.text
    remaining = int(response.headers["X-RateLimit-Remaining"])
    assert remaining == 10 - size, f"Expected {10-size} remaining after 5-event batch, got {remaining}"
    body = response.json()
    assert body["accepted"] == size
    assert len(body["event_ids"]) == size


async def test_free_tier_10_event_batch_succeeds(client: AsyncClient):
    token = await _login(client, "admin@local.dev", "adminadmin")
    headers = {"Authorization": f"Bearer {token}"}
    keys = await client.post(
        "/api/v1/auth/api-keys",
        headers=headers,
        json={"name": "batch-free-10", "rate_limit_tier": "free"},
    )
    assert keys.status_code == 201, keys.text
    api_key = keys.json()["api_key"]
    api_headers = {"X-API-Key": api_key}

    response = await client.post(
        "/api/v1/events/batch",
        headers=api_headers,
        json={"events": _make_batch_events(10)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] == 10
    remaining = int(response.headers["X-RateLimit-Remaining"])
    assert remaining == 0


async def test_free_tier_11_event_batch_returns_429(client: AsyncClient):
    token = await _login(client, "admin@local.dev", "adminadmin")
    headers = {"Authorization": f"Bearer {token}"}
    keys = await client.post(
        "/api/v1/auth/api-keys",
        headers=headers,
        json={"name": "batch-free-11", "rate_limit_tier": "free"},
    )
    assert keys.status_code == 201, keys.text
    api_key = keys.json()["api_key"]
    api_headers = {"X-API-Key": api_key}

    response = await client.post(
        "/api/v1/events/batch",
        headers=api_headers,
        json={"events": _make_batch_events(11)},
    )
    assert response.status_code == 429, response.text
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Reset" in response.headers
    assert "Retry-After" in response.headers
    assert "exceeds tier capacity" in response.json()["detail"]


async def test_single_event_cost_unchanged_after_fix(client: AsyncClient):
    token = await _login(client, "admin@local.dev", "adminadmin")
    headers = {"Authorization": f"Bearer {token}"}
    keys = await client.post(
        "/api/v1/auth/api-keys",
        headers=headers,
        json={"name": "single-unchanged", "rate_limit_tier": "free"},
    )
    assert keys.status_code == 201, keys.text
    api_key = keys.json()["api_key"]
    api_headers = {"X-API-Key": api_key}

    response = await client.post(
        "/api/v1/events",
        headers=api_headers,
        json={"event_type": "single", "payload": {}},
    )
    assert response.status_code == 200, response.text
    remaining = int(response.headers["X-RateLimit-Remaining"])
    assert remaining == 9
