"""Audio recordings: ambient sound or clinician voice notes.

Audio binary lives in MinIO. Voice notes may optionally be transcribed to
text via speech-to-text; the raw audio is always preserved.
"""

from datetime import datetime

from beanie import Document, Indexed, PydanticObjectId

from app.models.base import TimestampMixin
from app.models.enums import AudioKind, ProcessingStatus, TranscriptionStatus


class AudioRecording(Document, TimestampMixin):
    patient_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]
    kind: AudioKind = AudioKind.AMBIENT

    start_ts: datetime
    end_ts: datetime | None = None
    duration_seconds: float | None = None

    bucket: str
    object_key: str
    size_bytes: int | None = None
    format: str | None = None  # e.g. "wav", "ogg", "mp3"

    status: ProcessingStatus = ProcessingStatus.PENDING_UPLOAD

    # Speech-to-text.
    transcription: str | None = None
    transcription_status: TranscriptionStatus = TranscriptionStatus.NONE

    # For voice notes: who recorded it.
    recorded_by: PydanticObjectId | None = None

    class Settings:
        name = "audio_recordings"
