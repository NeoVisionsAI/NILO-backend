"""Schemas for session-wide MinIO download access bundles."""

from datetime import datetime
from typing import Literal

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

SessionMediaKind = Literal["video_segment", "audio", "landmarks", "pain_event"]


class SessionMediaItem(BaseModel):
    kind: SessionMediaKind
    id: PydanticObjectId
    bucket: str
    object_key: str
    download_url: str
    expires_in: int


class SessionMediaAccessOut(BaseModel):
    session_id: PydanticObjectId
    expires_in: int
    generated_at: datetime
    items: list[SessionMediaItem] = Field(default_factory=list)