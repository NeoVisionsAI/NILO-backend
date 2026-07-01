"""Pain event schemas."""

from datetime import datetime

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict

from app.models.enums import LandmarkSource, ProcessingStatus


class PainEventCreate(BaseModel):
    patient_id: PydanticObjectId
    start_ts: datetime
    end_ts: datetime | None = None
    duration_seconds: float | None = None
    severity: int | None = None
    notes: str | None = None
    landmarks_source: LandmarkSource = LandmarkSource.MEDIAPIPE
    file_extension: str = "mp4"


class PainEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    patient_id: PydanticObjectId
    start_ts: datetime
    end_ts: datetime | None = None
    duration_seconds: float | None = None
    bucket: str
    video_object_key: str
    landmarks_status: ProcessingStatus
    landmarks_source: LandmarkSource
    landmarks_object_key: str | None = None
    severity: int | None = None
    notes: str | None = None
    status: ProcessingStatus
