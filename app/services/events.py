import uuid
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import EventLog
from app.models.outbox import Outbox
from app.schemas.event import EventCreate


async def ingest_events(
    session: AsyncSession,
    user_id: uuid.UUID,
    events: list[EventCreate],
) -> list[uuid.UUID]:
    event_rows: list[dict[str, Any]] = []
    outbox_rows: list[dict[str, Any]] = []
    ids: list[uuid.UUID] = []
    for event in events:
        event_id = uuid.uuid4()
        ids.append(event_id)
        row = {
            "id": event_id,
            "user_id": user_id,
            "event_type": event.event_type,
            "payload": event.payload,
        }
        event_rows.append(row)
        outbox_rows.append(
            {
                "id": uuid.uuid4(),
                "event_id": event_id,
                "user_id": user_id,
                "event_type": event.event_type,
                "payload": event.payload,
                "status": "pending",
                "attempt_count": 0,
                "last_error": None,
            }
        )
    if event_rows:
        await session.execute(insert(EventLog), event_rows)
    if outbox_rows:
        await session.execute(insert(Outbox), outbox_rows)
    await session.commit()
    return ids


async def list_events(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[EventLog]:
    stmt = select(EventLog).order_by(EventLog.created_at.desc()).limit(limit)
    if user_id is not None:
        stmt = stmt.where(EventLog.user_id == user_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())
