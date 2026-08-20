import uuid
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import EventLog
from app.schemas.event import EventCreate


async def ingest_events(
    session: AsyncSession,
    user_id: uuid.UUID,
    events: list[EventCreate],
) -> list[uuid.UUID]:
    rows: list[dict[str, Any]] = []
    ids: list[uuid.UUID] = []
    for event in events:
        event_id = uuid.uuid4()
        ids.append(event_id)
        rows.append(
            {
                "id": event_id,
                "user_id": user_id,
                "event_type": event.event_type,
                "payload": event.payload,
            }
        )
    await session.execute(insert(EventLog), rows)
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
