"""Pain event endpoints.

A pain event registers a short video clip (uploaded to MinIO via presigned
URL) from which facial landmarks are later extracted for pain assessment.
"""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user, require_staff
from app.core.config import settings
from app.models.base import utcnow
from app.models.enums import ProcessingStatus
from app.models.pain_event import PainEvent
from app.models.user import User
from app.schemas.common import PresignedDownload
from app.schemas.pain_event import PainEventCreate, PainEventOut
from app.services.media_stream import streaming_response_for_object
from app.services.clinical_delete import delete_pain_event_record
from app.services.monitoring_session import require_active_ingestion
from app.services.presigned_download import mint_presigned_download
from app.storage import minio_client

router = APIRouter()


class _PainEventUploadResponse(PainEventOut):
    upload_url: str
    upload_expires_in: int


@router.post(
    "",
    response_model=_PainEventUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_pain_event(
    payload: PainEventCreate, current_user: User = Depends(require_staff)
) -> _PainEventUploadResponse:
    await require_active_ingestion(
        session_id=payload.session_id,
        patient_id=payload.patient_id,
        node_id=payload.node_id,
    )
    filename = f"pain_{int(payload.start_ts.timestamp())}.{payload.file_extension}"
    object_key = minio_client.build_object_key(
        patient_id=str(payload.patient_id),
        session_id=str(payload.session_id),
        modality=minio_client.MODALITY_VIDEO,
        filename=filename,
        ts=payload.start_ts,
    )
    event = PainEvent(
        session_id=payload.session_id,
        patient_id=payload.patient_id,
        node_id=payload.node_id,
        start_ts=payload.start_ts,
        end_ts=payload.end_ts,
        duration_seconds=payload.duration_seconds,
        bucket=settings.MINIO_BUCKET,
        video_object_key=object_key,
        severity=payload.severity,
        notes=payload.notes,
        landmarks_source=payload.landmarks_source,
        reported_by=current_user.id,
        status=ProcessingStatus.PENDING_UPLOAD,
    )
    await event.insert()
    upload_url = minio_client.presigned_put_url(object_key)
    return _PainEventUploadResponse(
        **PainEventOut.model_validate(event).model_dump(),
        upload_url=upload_url,
        upload_expires_in=settings.MINIO_PRESIGN_EXPIRY,
    )


@router.get("", response_model=list[PainEventOut])
async def list_pain_events(
    patient_id: PydanticObjectId,
    session_id: PydanticObjectId | None = None,
    node_id: PydanticObjectId | None = None,
    skip: int = 0,
    limit: int = 200,
    _: User = Depends(get_current_user),
) -> list[PainEvent]:
    conditions = [PainEvent.patient_id == patient_id]
    if session_id is not None:
        conditions.append(PainEvent.session_id == session_id)
    if node_id is not None:
        conditions.append(PainEvent.node_id == node_id)
    return (
        await PainEvent.find(*conditions)
        .sort(-PainEvent.start_ts)
        .skip(skip)
        .limit(limit)
        .to_list()
    )


@router.get("/{event_id}", response_model=PainEventOut)
async def get_pain_event(
    event_id: PydanticObjectId, _: User = Depends(get_current_user)
) -> PainEvent:
    event = await PainEvent.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Pain event not found")
    return event


@router.post("/{event_id}/confirm", response_model=PainEventOut)
async def confirm_pain_event_upload(
    event_id: PydanticObjectId, _: User = Depends(require_staff)
) -> PainEvent:
    event = await PainEvent.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Pain event not found")
    if not minio_client.object_exists(event.video_object_key, event.bucket):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Object not found in storage; upload not completed",
        )
    event.video_size_bytes = minio_client.stat_size(
        event.video_object_key, event.bucket
    )
    event.status = ProcessingStatus.UPLOADED
    # Facial landmark extraction is pending once the clip is available.
    event.landmarks_status = ProcessingStatus.PROCESSING
    event.updated_at = utcnow()
    await event.save()
    return event


@router.get("/{event_id}/download", response_model=PresignedDownload)
async def download_pain_event_video(
    event_id: PydanticObjectId,
    expires_in: int | None = None,
    _: User = Depends(get_current_user),
) -> PresignedDownload:
    event = await PainEvent.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Pain event not found")
    if not event.video_object_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pain event has no video object",
        )
    return mint_presigned_download(
        bucket=event.bucket,
        object_key=event.video_object_key,
        expiry_seconds=expires_in,
    )


@router.get("/{event_id}/file")
async def pain_event_video_file(
    event_id: PydanticObjectId,
    _: User = Depends(get_current_user),
) -> StreamingResponse:
    event = await PainEvent.get(event_id)
    if event is None or not event.video_object_key:
        raise HTTPException(status_code=404, detail="Pain event not found")
    return streaming_response_for_object(event.bucket, event.video_object_key)


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_pain_event(
    event_id: PydanticObjectId, _: User = Depends(require_staff)
) -> Response:
    event = await PainEvent.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Pain event not found")
    await delete_pain_event_record(event)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
