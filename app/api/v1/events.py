from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Principal,
    RateLimiter,
    consume_rate_limit,
    get_db,
    require_scopes,
)
from app.core.redis import get_redis
from app.models.user import UserRole
from app.schemas.event import EventBatchCreate, EventBatchResult, EventCreate, EventRead
from app.services.events import ingest_events, list_events
from app.services.rate_limiter import publish_events

router = APIRouter(prefix="/events", tags=["events"])


def _broadcast_payload(user_id: str, event_id: str, event: EventCreate) -> dict:
    return {
        "id": event_id,
        "user_id": user_id,
        "event_type": event.event_type,
        "payload": event.payload,
    }


@router.post("", response_model=EventRead, dependencies=[Depends(require_scopes("ingest_writer"))])
async def create_event(
    body: EventCreate,
    session: AsyncSession = Depends(get_db),
    principal: Principal = Depends(RateLimiter(cost=1)),
) -> EventRead:
    ids = await ingest_events(session, principal.user.id, [body])
    event_id = ids[0]
    await publish_events(
        get_redis(),
        [_broadcast_payload(str(principal.user.id), str(event_id), body)],
    )
    rows = await list_events(session, user_id=principal.user.id, limit=1)
    return rows[0]


@router.post(
    "/batch",
    response_model=EventBatchResult,
)
async def create_event_batch(
    body: EventBatchCreate,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_scopes("ingest_writer")),
) -> EventBatchResult:
    cost = len(body.events)
    principal = await consume_rate_limit(request, response, principal, cost)
    ids = await ingest_events(session, principal.user.id, body.events)
    messages = [
        _broadcast_payload(str(principal.user.id), str(event_id), event)
        for event_id, event in zip(ids, body.events, strict=True)
    ]
    await publish_events(get_redis(), messages)
    return EventBatchResult(accepted=len(ids), event_ids=ids)


@router.get("", response_model=list[EventRead], dependencies=[Depends(require_scopes("viewer"))])
async def get_events(
    session: AsyncSession = Depends(get_db),
    principal: Principal = Depends(RateLimiter(cost=1)),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[EventRead]:
    user_id = None if principal.user.role == UserRole.ADMIN else principal.user.id
    return await list_events(session, user_id=user_id, limit=limit)
