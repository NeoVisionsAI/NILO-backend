"""Body landmarks extracted from video (MediaPipe / YOLO).

Landmark data can be large (per-frame keypoints), so the payload is stored
as an object in MinIO and this document keeps the metadata plus a reference
to the source video segment when available.
"""

from datetime import datetime

from beanie import Document, Indexed, PydanticObjectId

from app.models.base import TimestampMixin
from app.models.enums import LandmarkSource, ProcessingStatus


class BodyLandmarks(Document, TimestampMixin):
    patient_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]
    # Optional link to the video segment the landmarks were extracted from.
    video_segment_id: PydanticObjectId | None = None

    source: LandmarkSource = LandmarkSource.MEDIAPIPE
    model_name: str | None = None  # e.g. "pose_landmarker_full"

    start_ts: datetime
    end_ts: datetime | None = None
    frame_count: int | None = None

    # Serialized landmark data (e.g. JSON/NPZ) in MinIO.
    bucket: str
    object_key: str
    size_bytes: int | None = None

    status: ProcessingStatus = ProcessingStatus.PROCESSED

    class Settings:
        name = "body_landmarks"
