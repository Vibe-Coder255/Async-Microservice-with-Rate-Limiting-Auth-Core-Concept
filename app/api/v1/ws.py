import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db_context
from app.core.redis import get_redis
from app.core.security import ROLE_SCOPES, decode_token
from app.models.user import User, UserRole

router = APIRouter(tags=["websocket"])


async def _authorize_socket(token: str | None) -> User:
    if not token:
        raise ValueError("Missing token")
    payload = decode_token(token)
    subject = payload.get("sub")
    if not subject:
        raise ValueError("Invalid token: missing sub")

    async with get_db_context() as session:
        result = await session.execute(select(User).where(User.id == UUID(subject)))
        user = result.scalar_one_or_none()
        if user is None:
            raise ValueError("User not found")
        if not user.is_active:
            raise ValueError("Inactive user")

    return user


@router.websocket("/events/stream")
async def event_stream(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    try:
        user = await _authorize_socket(token)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    allowed_scopes = ROLE_SCOPES[user.role.value]
    if user.role != UserRole.ADMIN and "viewer" not in allowed_scopes:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(settings.redis_events_channel)

    is_admin = user.role == UserRole.ADMIN
    own_user_id = str(user.id)

    async def pump_redis() -> None:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            try:
                event = json.loads(data) if isinstance(data, str) else data
            except (TypeError, json.JSONDecodeError):
                continue
            if not is_admin and isinstance(event, dict):
                event_user_id = event.get("user_id")
                if event_user_id != own_user_id:
                    continue
            await websocket.send_text(data if isinstance(data, str) else json.dumps(data))

    async def watch_client() -> None:
        while True:
            await websocket.receive_text()

    try:
        pump = asyncio.create_task(pump_redis())
        watch = asyncio.create_task(watch_client())
        done, pending = await asyncio.wait(
            {pump, watch}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception() if not task.cancelled() else None
            if exc and not isinstance(exc, WebSocketDisconnect):
                raise exc
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(settings.redis_events_channel)
        await pubsub.aclose()
