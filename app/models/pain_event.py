"""Pain episode events.

A pain event is essentially a short video clip from which facial landmarks
are later extracted (e.g. with MediaPipe) to assess pain. The clip lives in
MinIO; extracted landmarks are stored as a separate object referenced here.
"""

from datetime import datetime

from beanie import Document, Indexed, PydanticObjectId

from app.models.base import TimestampMixin
from app.models.enums import LandmarkSource, ProcessingStatus


class PainEvent(Document, TimestampMixin):
    patient_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]

    start_ts: datetime
    end_ts: datetime | None = None
    duration_seconds: float | None = None

    # Video clip of the episode in MinIO.
    bucket: str
    video_object_key: str
    video_size_bytes: int | None = None

    # Facial landmarks extracted from the clip.
    landmarks_status: ProcessingStatus = ProcessingStatus.PENDING_UPLOAD
    landmarks_source: LandmarkSource = LandmarkSource.MEDIAPIPE
    landmarks_object_key: str | None = None

    # Optional clinical annotations.
    severity: int | None = None  # e.g. 0-10 pain scale
    notes: str | None = None
    reported_by: PydanticObjectId | None = None

    status: ProcessingStatus = ProcessingStatus.PENDING_UPLOAD

    class Settings:
        name = "pain_events"
