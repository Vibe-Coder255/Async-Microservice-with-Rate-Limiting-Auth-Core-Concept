import asyncio
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.config import settings
from app.core.redis import get_redis
from app.core.security import decode_token
from app.models.user import UserRole

router = APIRouter(tags=["websocket"])


async def _authorize_socket(token: str | None) -> None:
    if not token:
        raise ValueError("Missing token")
    payload = decode_token(token)
    scopes = payload.get("scopes") or []
    role = payload.get("role")
    if role != UserRole.ADMIN.value and "viewer" not in scopes:
        raise ValueError("Missing viewer scope")


@router.websocket("/events/stream")
async def event_stream(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    try:
        await _authorize_socket(token)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(settings.redis_events_channel)

    async def pump_redis() -> None:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8")
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
