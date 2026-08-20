from fastapi import APIRouter

from app.api.v1 import auth, events, ws

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(events.router)
api_router.include_router(ws.router)
