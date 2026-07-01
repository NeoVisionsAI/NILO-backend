"""Video recording sessions and segment (chunk) management.

Upload flow (presigned):
1. Client creates a Recording (session) for a patient.
2. For each chunk, client POSTs segment metadata and gets a presigned PUT URL
   plus a VideoSegment document (status ``pending_upload``).
3. Client uploads the binary directly to MinIO using that URL.
4. Client confirms upload; the backend verifies the object and flips the
   status to ``uploaded``.
"""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_staff
from app.core.config import settings
from app.models.base import utcnow
from app.models.enums import ProcessingStatus, RecordingStatus
from app.models.recording import Recording, VideoSegment
from app.models.user import User
from app.schemas.common import PresignedDownload, PresignedUpload
from app.schemas.recording import (
    RecordingCreate,
    RecordingOut,
    SegmentOut,
    SegmentUploadRequest,
    SegmentUploadResponse,
)
from app.storage import minio_client

router = APIRouter()


@router.post(
    "", response_model=RecordingOut, status_code=status.HTTP_201_CREATED
)
async def create_recording(
    payload: RecordingCreate, _: User = Depends(require_staff)
) -> Recording:
    recording = Recording(
        patient_id=payload.patient_id,
        device_id=payload.device_id,
        archive_chunk_seconds=payload.archive_chunk_seconds
        or settings.DEFAULT_VIDEO_CHUNK_SECONDS,
        hls_segment_seconds=payload.hls_segment_seconds
        or settings.DEFAULT_HLS_SEGMENT_SECONDS,
    )
    await recording.insert()
    return recording


@router.get("", response_model=list[RecordingOut])
async def list_recordings(
    patient_id: PydanticObjectId | None = None,
    skip: int = 0,
    limit: int = 100,
    _: User = Depends(get_current_user),
) -> list[Recording]:
    query = (
        Recording.find(Recording.patient_id == patient_id)
        if patient_id
        else Recording.find_all()
    )
    return await query.sort(-Recording.started_at).skip(skip).limit(limit).to_list()


@router.get("/{recording_id}", response_model=RecordingOut)
async def get_recording(
    recording_id: PydanticObjectId, _: User = Depends(get_current_user)
) -> Recording:
    recording = await Recording.get(recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    return recording


@router.post("/{recording_id}/end", response_model=RecordingOut)
async def end_recording(
    recording_id: PydanticObjectId, _: User = Depends(require_staff)
) -> Recording:
    recording = await Recording.get(recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    recording.status = RecordingStatus.COMPLETED
    recording.ended_at = utcnow()
    recording.updated_at = utcnow()
    await recording.save()
    return recording


@router.post(
    "/{recording_id}/segments",
    response_model=SegmentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_segment_upload(
    recording_id: PydanticObjectId,
    payload: SegmentUploadRequest,
    _: User = Depends(require_staff),
) -> SegmentUploadResponse:
    recording = await Recording.get(recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")

    filename = f"{payload.seq:06d}_{int(payload.start_ts.timestamp())}.{payload.file_extension}"
    object_key = minio_client.build_object_key(
        patient_id=str(recording.patient_id),
        category="video",
        filename=filename,
        ts=payload.start_ts,
        subpath=str(recording.id),
    )

    segment = VideoSegment(
        recording_id=recording.id,
        patient_id=recording.patient_id,
        seq=payload.seq,
        kind=payload.kind,
        fmt=payload.fmt,
        start_ts=payload.start_ts,
        end_ts=payload.end_ts,
        duration_seconds=payload.duration_seconds,
        bucket=settings.MINIO_BUCKET,
        object_key=object_key,
        codec=payload.codec,
        width=payload.width,
        height=payload.height,
        fps=payload.fps,
        status=ProcessingStatus.PENDING_UPLOAD,
    )
    await segment.insert()

    upload_url = minio_client.presigned_put_url(object_key)
    return SegmentUploadResponse(
        segment=SegmentOut.model_validate(segment),
        upload=PresignedUpload(
            bucket=settings.MINIO_BUCKET,
            object_key=object_key,
            upload_url=upload_url,
            expires_in=settings.MINIO_PRESIGN_EXPIRY,
        ),
    )


@router.get("/{recording_id}/segments", response_model=list[SegmentOut])
async def list_segments(
    recording_id: PydanticObjectId,
    skip: int = 0,
    limit: int = 500,
    _: User = Depends(get_current_user),
) -> list[VideoSegment]:
    return (
        await VideoSegment.find(VideoSegment.recording_id == recording_id)
        .sort(+VideoSegment.seq)
        .skip(skip)
        .limit(limit)
        .to_list()
    )


@router.post("/segments/{segment_id}/confirm", response_model=SegmentOut)
async def confirm_segment_upload(
    segment_id: PydanticObjectId, _: User = Depends(require_staff)
) -> VideoSegment:
    segment = await VideoSegment.get(segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    if not minio_client.object_exists(segment.object_key, segment.bucket):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Object not found in storage; upload not completed",
        )
    segment.size_bytes = minio_client.stat_size(
        segment.object_key, segment.bucket
    )
    segment.status = ProcessingStatus.UPLOADED
    segment.updated_at = utcnow()
    await segment.save()
    return segment


@router.get(
    "/segments/{segment_id}/download", response_model=PresignedDownload
)
async def download_segment(
    segment_id: PydanticObjectId, _: User = Depends(get_current_user)
) -> PresignedDownload:
    segment = await VideoSegment.get(segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    url = minio_client.presigned_get_url(segment.object_key, segment.bucket)
    return PresignedDownload(
        bucket=segment.bucket,
        object_key=segment.object_key,
        download_url=url,
        expires_in=settings.MINIO_PRESIGN_EXPIRY,
    )
