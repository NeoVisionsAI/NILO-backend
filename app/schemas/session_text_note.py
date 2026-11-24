"""Session text note API schemas."""

from datetime import datetime

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


class SessionTextNoteCreate(BaseModel):
    patient_id: PydanticObjectId
    node_id: PydanticObjectId | None = Field(
        None,
        description="ObjectId del nodo NILO, si se conoce",
    )
    body: str = Field(..., min_length=1, max_length=20000)
    recorded_at: datetime | None = None


class SessionTextNoteUpdate(BaseModel):
    body: str = Field(..., min_length=1, max_length=20000)


class SessionTextNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    session_id: PydanticObjectId
    patient_id: PydanticObjectId
    node_id: PydanticObjectId | None = None
    body: str
    recorded_at: datetime
    author_id: PydanticObjectId | None = None
    created_at: datetime
    updated_at: datetime