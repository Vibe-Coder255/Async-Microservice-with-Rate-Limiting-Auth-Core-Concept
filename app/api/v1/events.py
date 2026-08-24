from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Principal,
    RateLimiter,
    consume_rate_limit,
    get_db,
    require_scopes,
)
from app.models.user import UserRole
from app.schemas.event import EventBatchCreate, EventBatchResult, EventCreate, EventRead
from app.services.events import ingest_events, list_events

router = APIRouter(tags=["events"])


@router.post(
    "",
    response_model=EventRead,
    dependencies=[Depends(require_scopes("ingest_writer"))],
)
async def create_event(
    body: EventCreate,
    session: AsyncSession = Depends(get_db),
    principal: Principal = Depends(RateLimiter(cost=1)),
) -> EventRead:
    [event_id] = await ingest_events(session, principal.user.id, [body])
    return EventRead(
        id=event_id,
        user_id=principal.user.id,
        event_type=body.event_type,
        payload=body.payload,
    )


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
    return EventBatchResult(accepted=len(ids), event_ids=ids)


@router.get("", response_model=list[EventRead])
async def list_events_view(
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_scopes("viewer")),
) -> list[EventRead]:
    user_id = None if principal.user.role == UserRole.ADMIN else principal.user.id
    rows = await list_events(session, user_id=user_id, limit=limit)
    return [
        EventRead(
            id=row.id,
            user_id=row.user_id,
            event_type=row.event_type,
            payload=row.payload,
            created_at=row.created_at,
        )
        for row in rows
    ]
