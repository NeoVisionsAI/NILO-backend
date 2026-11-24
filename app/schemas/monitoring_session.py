"""Monitoring session and video segment API schemas."""

from datetime import datetime

from beanie import PydanticObjectId
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import (
    MonitoringSessionStatus,
    ProcessingStatus,
    SegmentFormat,
    SegmentKind,
)
from app.schemas.common import PresignedUpload


class MonitoringSessionCreate(BaseModel):
    patient_id: PydanticObjectId
    node_id: PydanticObjectId | None = Field(
        None,
        description="ObjectId del nodo NILO (dispositivo de captura), si se conoce",
    )
    external_session_id: str | None = Field(
        None,
        description="Client-side session id (e.g. UUID from nilo-node)",
    )
    archive_chunk_seconds: int | None = None
    hls_segment_seconds: int | None = None


class MonitoringSessionUpdate(BaseModel):
    """Staff-only metadata patch (does not change ids or ingestion correlation)."""

    display_name: str | None = Field(
        None,
        description="Human label; null clears it. 1–120 characters when set.",
    )

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        if len(stripped) > 120:
            raise ValueError("display_name must be at most 120 characters")
        return stripped


class MonitoringSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    patient_id: PydanticObjectId
    node_id: PydanticObjectId | None = None
    external_session_id: str | None = None
    display_name: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    status: MonitoringSessionStatus
    archive_chunk_seconds: int
    hls_segment_seconds: int
    hls_manifest_key: str | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def legacy_session_fields(cls, data: Any) -> Any:
        """Coerce documents written before TimestampMixin or pipeline defaults."""
        if hasattr(data, "model_dump"):
            data = data.model_dump()
        if not isinstance(data, dict):
            return data
        started = data.get("started_at")
        if data.get("created_at") is None and started is not None:
            data["created_at"] = started
        if data.get("updated_at") is None:
            data["updated_at"] = data.get("created_at") or started
        if data.get("archive_chunk_seconds") is None:
            data["archive_chunk_seconds"] = 300
        if data.get("hls_segment_seconds") is None:
            data["hls_segment_seconds"] = 6
        return data


class SessionOverviewOut(BaseModel):
    session: MonitoringSessionOut
    video_segments: int
    audio_clips: int
    physiological_readings: int
    landmarks_batches: int
    pain_events: int
    text_notes: int


class SegmentUploadRequest(BaseModel):
    node_id: PydanticObjectId | None = Field(
        None,
        description="ObjectId del nodo NILO que genera el segmento, si se conoce",
    )
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
    session_id: PydanticObjectId
    patient_id: PydanticObjectId
    node_id: PydanticObjectId | None = None
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
    segment: SegmentOut
    upload: PresignedUpload
