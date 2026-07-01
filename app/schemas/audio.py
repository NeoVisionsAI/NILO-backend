"""Audio recording schemas."""

from datetime import datetime

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict

from app.models.enums import AudioKind, ProcessingStatus, TranscriptionStatus


class AudioUploadRequest(BaseModel):
    patient_id: PydanticObjectId
    kind: AudioKind = AudioKind.AMBIENT
    start_ts: datetime
    end_ts: datetime | None = None
    duration_seconds: float | None = None
    format: str = "wav"
    file_extension: str = "wav"


class AudioTranscriptionUpdate(BaseModel):
    transcription: str
    transcription_status: TranscriptionStatus = TranscriptionStatus.DONE


class AudioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    patient_id: PydanticObjectId
    kind: AudioKind
    start_ts: datetime
    end_ts: datetime | None = None
    duration_seconds: float | None = None
    bucket: str
    object_key: str
    size_bytes: int | None = None
    format: str | None = None
    status: ProcessingStatus
    transcription: str | None = None
    transcription_status: TranscriptionStatus
