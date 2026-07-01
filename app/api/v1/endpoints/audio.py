"""Audio recording endpoints (ambient sound and voice notes).

Raw audio is uploaded to MinIO via presigned URL. Voice notes can later be
transcribed to text (speech-to-text) while the original audio is preserved.
"""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_staff
from app.core.config import settings
from app.models.audio import AudioRecording
from app.models.base import utcnow
from app.models.enums import ProcessingStatus, TranscriptionStatus
from app.models.user import User
from app.schemas.audio import (
    AudioOut,
    AudioTranscriptionUpdate,
    AudioUploadRequest,
)
from app.schemas.common import PresignedDownload, PresignedUpload
from app.storage import minio_client

router = APIRouter()


@router.post("", response_model=PresignedUpload, status_code=status.HTTP_201_CREATED)
async def request_audio_upload(
    payload: AudioUploadRequest, current_user: User = Depends(require_staff)
) -> PresignedUpload:
    filename = f"{int(payload.start_ts.timestamp())}_{payload.kind.value}.{payload.file_extension}"
    object_key = minio_client.build_object_key(
        patient_id=str(payload.patient_id),
        category="audio",
        filename=filename,
        ts=payload.start_ts,
    )
    audio = AudioRecording(
        patient_id=payload.patient_id,
        kind=payload.kind,
        start_ts=payload.start_ts,
        end_ts=payload.end_ts,
        duration_seconds=payload.duration_seconds,
        bucket=settings.MINIO_BUCKET,
        object_key=object_key,
        format=payload.format,
        status=ProcessingStatus.PENDING_UPLOAD,
        recorded_by=current_user.id,
    )
    await audio.insert()
    upload_url = minio_client.presigned_put_url(object_key)
    return PresignedUpload(
        bucket=settings.MINIO_BUCKET,
        object_key=object_key,
        upload_url=upload_url,
        expires_in=settings.MINIO_PRESIGN_EXPIRY,
    )


@router.get("", response_model=list[AudioOut])
async def list_audio(
    patient_id: PydanticObjectId,
    skip: int = 0,
    limit: int = 200,
    _: User = Depends(get_current_user),
) -> list[AudioRecording]:
    return (
        await AudioRecording.find(AudioRecording.patient_id == patient_id)
        .sort(-AudioRecording.start_ts)
        .skip(skip)
        .limit(limit)
        .to_list()
    )


@router.get("/{audio_id}", response_model=AudioOut)
async def get_audio(
    audio_id: PydanticObjectId, _: User = Depends(get_current_user)
) -> AudioRecording:
    audio = await AudioRecording.get(audio_id)
    if audio is None:
        raise HTTPException(status_code=404, detail="Audio not found")
    return audio


@router.post("/{audio_id}/confirm", response_model=AudioOut)
async def confirm_audio_upload(
    audio_id: PydanticObjectId, _: User = Depends(require_staff)
) -> AudioRecording:
    audio = await AudioRecording.get(audio_id)
    if audio is None:
        raise HTTPException(status_code=404, detail="Audio not found")
    if not minio_client.object_exists(audio.object_key, audio.bucket):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Object not found in storage; upload not completed",
        )
    audio.size_bytes = minio_client.stat_size(audio.object_key, audio.bucket)
    audio.status = ProcessingStatus.UPLOADED
    if audio.kind.value == "voice_note":
        audio.transcription_status = TranscriptionStatus.PENDING
    audio.updated_at = utcnow()
    await audio.save()
    return audio


@router.patch("/{audio_id}/transcription", response_model=AudioOut)
async def set_transcription(
    audio_id: PydanticObjectId,
    payload: AudioTranscriptionUpdate,
    _: User = Depends(require_staff),
) -> AudioRecording:
    audio = await AudioRecording.get(audio_id)
    if audio is None:
        raise HTTPException(status_code=404, detail="Audio not found")
    audio.transcription = payload.transcription
    audio.transcription_status = payload.transcription_status
    audio.updated_at = utcnow()
    await audio.save()
    return audio


@router.get("/{audio_id}/download", response_model=PresignedDownload)
async def download_audio(
    audio_id: PydanticObjectId, _: User = Depends(get_current_user)
) -> PresignedDownload:
    audio = await AudioRecording.get(audio_id)
    if audio is None:
        raise HTTPException(status_code=404, detail="Audio not found")
    url = minio_client.presigned_get_url(audio.object_key, audio.bucket)
    return PresignedDownload(
        bucket=audio.bucket,
        object_key=audio.object_key,
        download_url=url,
        expires_in=settings.MINIO_PRESIGN_EXPIRY,
    )
