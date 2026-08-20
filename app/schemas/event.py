from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)


class EventBatchCreate(BaseModel):
    events: list[EventCreate] = Field(min_length=1, max_length=1000)


class EventRead(BaseModel):
    id: UUID
    user_id: UUID
    event_type: str
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class EventBatchResult(BaseModel):
    accepted: int
    event_ids: list[UUID]
