"""Video recording session and its video segments (chunks).

Hybrid strategy:
- A ``Recording`` groups a continuous monitoring session for a patient.
- ``VideoSegment`` documents describe the individual chunks. Short ``LIVE``
  segments feed an HLS playlist for live viewing; longer ``ARCHIVE`` chunks
  are the consolidated files kept for long-term storage / post-processing.

The binary payload always lives in MinIO; MongoDB only stores metadata and
the object key. Everything is correlated with other data sources through
``patient_id`` + UTC timestamps (``start_ts`` / ``end_ts``).
"""

from datetime import datetime

from beanie import Document, Indexed, PydanticObjectId
from pydantic import Field

from app.models.base import TimestampMixin, utcnow
from app.models.enums import (
    ProcessingStatus,
    RecordingStatus,
    SegmentFormat,
    SegmentKind,
)


class Recording(Document, TimestampMixin):
    patient_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]
    device_id: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None
    status: RecordingStatus = RecordingStatus.ACTIVE

    # Configured chunk sizes for this session.
    archive_chunk_seconds: int = 300
    hls_segment_seconds: int = 6

    # Object key of the live HLS manifest (.m3u8) in MinIO, if any.
    hls_manifest_key: str | None = None

    class Settings:
        name = "recordings"


class VideoSegment(Document, TimestampMixin):
    recording_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]
    patient_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]

    # Monotonic sequence number within the recording.
    seq: int = 0
    kind: SegmentKind = SegmentKind.ARCHIVE
    fmt: SegmentFormat = SegmentFormat.FMP4

    start_ts: datetime
    end_ts: datetime | None = None
    duration_seconds: float | None = None

    # MinIO location + payload metadata.
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
