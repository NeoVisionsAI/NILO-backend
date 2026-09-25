"""Monitoring session and video segments.

A **MonitoringSession** is the top-level container for a period of patient
monitoring (from minutes to multi-day 24/7). Video, audio, vitals, landmarks
and pain events are **partial** in time: each modality carries its own
``start_ts`` / ``timestamp`` and optional ``session_id``.

Binary video payloads live in MinIO; MongoDB stores metadata and object keys.
"""

from datetime import datetime

from beanie import Document, Indexed, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.base import TimestampMixin, utcnow
from app.models.enums import (
    MonitoringSessionStatus,
    ProcessingStatus,
    SegmentFormat,
    SegmentKind,
)


class MonitoringSession(Document, TimestampMixin):
    patient_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]
    # NILO node (capture device) when known.
    node_id: PydanticObjectId | None = None
    # External id from nilo-node (UUID) for correlation on the device side.
    external_session_id: str | None = None

    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None
    status: MonitoringSessionStatus = MonitoringSessionStatus.ACTIVE

    # Video pipeline defaults for this session (chunks may cover only part of it).
    archive_chunk_seconds: int = 300
    hls_segment_seconds: int = 6
    hls_manifest_key: str | None = None

    class Settings:
        name = "monitoring_sessions"
        indexes = [
            IndexModel([("patient_id", ASCENDING), ("started_at", DESCENDING)]),
            IndexModel([("node_id", ASCENDING), ("started_at", DESCENDING)]),
            IndexModel([("status", ASCENDING)]),
        ]


class VideoSegment(Document, TimestampMixin):
    session_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]
    patient_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]
    node_id: PydanticObjectId | None = None

    seq: int = 0
    kind: SegmentKind = SegmentKind.ARCHIVE
    fmt: SegmentFormat = SegmentFormat.FMP4

    start_ts: datetime
    end_ts: datetime | None = None
    duration_seconds: float | None = None

    bucket: str
    object_key: str
    size_bytes: int | None = None
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None

    status: ProcessingStatus = ProcessingStatus.PENDING_UPLOAD

    class Settings:
        name = "video_segments"
        indexes = [
            IndexModel([("session_id", ASCENDING), ("seq", ASCENDING)]),
        ]
