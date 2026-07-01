"""Recording and video segment schemas."""

from datetime import datetime

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    ProcessingStatus,
    RecordingStatus,
    SegmentFormat,
    SegmentKind,
)
from app.schemas.common import PresignedUpload


class RecordingCreate(BaseModel):
    patient_id: PydanticObjectId
    device_id: str | None = None
    archive_chunk_seconds: int | None = None
    hls_segment_seconds: int | None = None


class RecordingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    patient_id: PydanticObjectId
    device_id: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    status: RecordingStatus
    archive_chunk_seconds: int
    hls_segment_seconds: int
    hls_manifest_key: str | None = None


class SegmentUploadRequest(BaseModel):
    """Client asks for a presigned URL to upload a new video chunk."""

    seq: int = 0
    kind: SegmentKind = SegmentKind.ARCHIVE
    fmt: SegmentFormat = SegmentFormat.FMP4
    start_ts: datetime
    end_ts: datetime | None = None
    duration_seconds: float | None = None
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    file_extension: str = "mp4"


class SegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    recording_id: PydanticObjectId
    patient_id: PydanticObjectId
    seq: int
    kind: SegmentKind
    fmt: SegmentFormat
    start_ts: datetime
    end_ts: datetime | None = None
    duration_seconds: float | None = None
    bucket: str
    object_key: str
    size_bytes: int | None = None
    status: ProcessingStatus


class SegmentUploadResponse(BaseModel):
    """Segment metadata plus the presigned URL to upload its binary."""

    segment: SegmentOut
    upload: PresignedUpload
