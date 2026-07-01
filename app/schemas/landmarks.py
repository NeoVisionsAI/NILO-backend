"""Body landmarks schemas."""

from datetime import datetime

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict

from app.models.enums import LandmarkSource, ProcessingStatus


class LandmarksUploadRequest(BaseModel):
    patient_id: PydanticObjectId
    video_segment_id: PydanticObjectId | None = None
    source: LandmarkSource = LandmarkSource.MEDIAPIPE
    model_name: str | None = None
    start_ts: datetime
    end_ts: datetime | None = None
    frame_count: int | None = None
    file_extension: str = "json"


class LandmarksOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    patient_id: PydanticObjectId
    video_segment_id: PydanticObjectId | None = None
    source: LandmarkSource
    model_name: str | None = None
    start_ts: datetime
    end_ts: datetime | None = None
    frame_count: int | None = None
    bucket: str
    object_key: str
    size_bytes: int | None = None
    status: ProcessingStatus
