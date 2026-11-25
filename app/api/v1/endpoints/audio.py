"""Audio recording endpoints (ambient sound and voice notes).

Raw audio is uploaded to MinIO via presigned URL. Voice notes can later be
transcribed to text (speech-to-text) while the original audio is preserved.
"""

from datetime import datetime
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.deps import get_current_user, require_staff
from app.core.config import settings
from app.core.upload_body import read_proxy_upload_bytes
from app.models.audio import AudioRecording
from app.models.base import utcnow
from app.models.enums import AudioKind, ProcessingStatus, TranscriptionStatus
from app.models.user import User
from app.schemas.audio import (
    AudioOut,
    AudioTranscriptionUpdate,
    AudioUploadRequest,
    AudioUploadResponse,
)
from app.schemas.common import PresignedDownload
from app.services.monitoring_session import require_active_ingestion
from app.storage import minio_client

router = APIRouter()


@router.post(
    "/upload", response_model=AudioOut, status_code=status.HTTP_201_CREATED
)
async def upload_audio_body(
    session_id: Annotated[PydanticObjectId, Form()],
    patient_id: Annotated[PydanticObjectId, Form()],
    start_ts: Annotated[datetime, Form()],
    file: UploadFile = File(...),
    kind: AudioKind = Form(AudioKind.VOICE_NOTE),
    node_id: Annotated[PydanticObjectId | None, Form()] = None,
    end_ts: Annotated[datetime | None, Form()] = None,
    duration_seconds: Annotated[float | None, Form()] = None,
    file_extension: Annotated[str, Form()] = "webm",
    format: Annotated[str | None, Form()] = None,
    current_user: User = Depends(require_staff),
) -> AudioRecording:
    """Multipart upload: API writes audio to MinIO."""
    await require_active_ingestion(
        session_id=session_id,
        patient_id=patient_id,
        node_id=node_id,
    )
    data = await read_proxy_upload_bytes(file)
    filename = f"{int(start_ts.timestamp())}_{kind.value}.{file_extension}"
    modality = (
        minio_client.MODALITY_AUDIO_NOTES
        if kind == AudioKind.VOICE_NOTE
        else minio_client.MODALITY_AUDIO
    )
    object_key = minio_client.build_object_key(
        patient_id=str(patient_id),
        session_id=str(session_id),
        modality=modality,
        filename=filename,
        ts=start_ts,
    )
    content_type = file.content_type or "application/octet-stream"
    size = minio_client.put_object_bytes(object_key, data, content_type=content_type)
    audio = AudioRecording(
        session_id=session_id,
        patient_id=patient_id,
        node_id=node_id,
        kind=kind,
        start_ts=start_ts,
        end_ts=end_ts,
        duration_seconds=duration_seconds,
        bucket=settings.MINIO_BUCKET,
        object_key=object_key,
        size_bytes=size,
        format=format,
        status=ProcessingStatus.UPLOADED,
        recorded_by=current_user.id,
    )
    if kind == AudioKind.VOICE_NOTE:
        audio.transcription_status = TranscriptionStatus.PENDING
    await audio.insert()
    return audio


@router.post(
    "", response_model=AudioUploadResponse, status_code=status.HTTP_201_CREATED
)
async def request_audio_upload(
    payload: AudioUploadRequest, current_user: User = Depends(require_staff)
) -> AudioUploadResponse:
    await require_active_ingestion(
        session_id=payload.session_id,
        patient_id=payload.patient_id,
        node_id=payload.node_id,
    )
    filename = f"{int(payload.start_ts.timestamp())}_{payload.kind.value}.{payload.file_extension}"
    modality = (
        minio_client.MODALITY_AUDIO_NOTES
        if payload.kind == AudioKind.VOICE_NOTE
        else minio_client.MODALITY_AUDIO
    )
    object_key = minio_client.build_object_key(
        patient_id=str(payload.patient_id),
        session_id=str(payload.session_id),
        modality=modality,
        filename=filename,
        ts=payload.start_ts,
    )
    audio = AudioRecording(
        session_id=payload.session_id,
        patient_id=payload.patient_id,
        node_id=payload.node_id,
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
    return AudioUploadResponse(
        id=audio.id,
        bucket=settings.MINIO_BUCKET,
        object_key=object_key,
        upload_url=upload_url,
        expires_in=settings.MINIO_PRESIGN_EXPIRY,
    )


@router.get("", response_model=list[AudioOut])
async def list_audio(
    patient_id: PydanticObjectId,
    session_id: PydanticObjectId | None = None,
    node_id: PydanticObjectId | None = None,
    skip: int = 0,
    limit: int = 200,
    _: User = Depends(get_current_user),
) -> list[AudioRecording]:
    conditions = [AudioRecording.patient_id == patient_id]
    if session_id is not None:
        conditions.append(AudioRecording.session_id == session_id)
    if node_id is not None:
        conditions.append(AudioRecording.node_id == node_id)
    return (
        await AudioRecording.find(*conditions)
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
        expires_in=settings.MINIO_DOWNLOAD_EXPIRY,
    )
