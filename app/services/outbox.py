import asyncio
import json
import uuid
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_context
from app.core.redis import get_redis
from app.models.outbox import Outbox
from app.services.rate_limiter import publish_events

MAX_ATTEMPTS = 5
POLL_INTERVAL_SEC = 0.25
BATCH_SIZE = 100


def _broadcast_payload(user_id: str, event_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "user_id": user_id,
        "event_type": event_type,
        "payload": payload,
    }


async def _claim_pending(session: AsyncSession, limit: int) -> list[Outbox]:
    stmt = (
        select(Outbox)
        .where(Outbox.status.in_(["pending", "failed"]))
        .where(Outbox.attempt_count < MAX_ATTEMPTS)
        .order_by(Outbox.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    if rows:
        ids = [r.id for r in rows]
        await session.execute(
            update(Outbox)
            .where(Outbox.id.in_(ids))
            .values(attempt_count=Outbox.attempt_count + 1)
        )
        await session.commit()
    return rows


async def _mark_published(session: AsyncSession, ids: list[uuid.UUID]) -> None:
    if not ids:
        return
    await session.execute(
        update(Outbox)
        .where(Outbox.id.in_(ids))
        .values(status="published", last_error=None)
    )
    await session.commit()


async def _mark_failed(session: AsyncSession, failed_rows: list[tuple[Outbox, str]]) -> None:
    if not failed_rows:
        return
    for row, err in failed_rows:
        await session.execute(
            update(Outbox)
            .where(Outbox.id == row.id)
            .values(status="failed", last_error=err)
        )
    await session.commit()


async def _process_batch(redis: Redis) -> None:
    published_ids: list[uuid.UUID] = []
    failed_rows: list[tuple[Outbox, str]] = []

    async with get_db_context() as session:
        rows = await _claim_pending(session, BATCH_SIZE)
        if not rows:
            return

    messages: list[dict[str, Any]] = []
    for row in rows:
        try:
            msg = _broadcast_payload(
                user_id=str(row.user_id),
                event_id=str(row.event_id),
                event_type=row.event_type,
                payload=row.payload,
            )
            messages.append(msg)
            published_ids.append(row.id)
        except Exception as exc:  # noqa: BLE001
            failed_rows.append((row, f"prepare: {exc!r}"))

    publish_error: str | None = None
    try:
        await publish_events(redis, messages)
    except Exception as exc:  # noqa: BLE001
        publish_error = f"publish: {exc!r}"

    async with get_db_context() as session:
        if publish_error is None:
            await _mark_published(session, published_ids)
        else:
            for row in rows:
                failed_rows.append((row, publish_error))
            published_ids = []
        await _mark_failed(session, failed_rows)


async def outbox_worker(stop_event: asyncio.Event) -> None:
    redis = get_redis()
    while not stop_event.is_set():
        try:
            await _process_batch(redis)
        except Exception:  # noqa: BLE001
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_INTERVAL_SEC)
        except asyncio.TimeoutError:
            pass
