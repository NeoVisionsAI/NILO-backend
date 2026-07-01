"""Body landmarks endpoints (MediaPipe / YOLO).

Landmark payloads (per-frame keypoints) are uploaded to MinIO via presigned
URL; this document keeps the metadata and a link to the source video segment.
"""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_staff
from app.core.config import settings
from app.models.base import utcnow
from app.models.enums import ProcessingStatus
from app.models.landmarks import BodyLandmarks
from app.models.user import User
from app.schemas.common import PresignedDownload
from app.schemas.landmarks import LandmarksOut, LandmarksUploadRequest
from app.storage import minio_client

router = APIRouter()


class _LandmarksUploadResponse(LandmarksOut):
    upload_url: str
    upload_expires_in: int


@router.post(
    "",
    response_model=_LandmarksUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_landmarks_upload(
    payload: LandmarksUploadRequest, _: User = Depends(require_staff)
) -> _LandmarksUploadResponse:
    filename = f"landmarks_{int(payload.start_ts.timestamp())}_{payload.source.value}.{payload.file_extension}"
    object_key = minio_client.build_object_key(
        patient_id=str(payload.patient_id),
        category="landmarks",
        filename=filename,
        ts=payload.start_ts,
    )
    doc = BodyLandmarks(
        patient_id=payload.patient_id,
        video_segment_id=payload.video_segment_id,
        source=payload.source,
        model_name=payload.model_name,
        start_ts=payload.start_ts,
        end_ts=payload.end_ts,
        frame_count=payload.frame_count,
        bucket=settings.MINIO_BUCKET,
        object_key=object_key,
        status=ProcessingStatus.PENDING_UPLOAD,
    )
    await doc.insert()
    upload_url = minio_client.presigned_put_url(object_key)
    return _LandmarksUploadResponse(
        **LandmarksOut.model_validate(doc).model_dump(),
        upload_url=upload_url,
        upload_expires_in=settings.MINIO_PRESIGN_EXPIRY,
    )


@router.get("", response_model=list[LandmarksOut])
async def list_landmarks(
    patient_id: PydanticObjectId,
    skip: int = 0,
    limit: int = 200,
    _: User = Depends(get_current_user),
) -> list[BodyLandmarks]:
    return (
        await BodyLandmarks.find(BodyLandmarks.patient_id == patient_id)
        .sort(-BodyLandmarks.start_ts)
        .skip(skip)
        .limit(limit)
        .to_list()
    )


@router.post("/{landmarks_id}/confirm", response_model=LandmarksOut)
async def confirm_landmarks_upload(
    landmarks_id: PydanticObjectId, _: User = Depends(require_staff)
) -> BodyLandmarks:
    doc = await BodyLandmarks.get(landmarks_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Landmarks not found")
    if not minio_client.object_exists(doc.object_key, doc.bucket):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Object not found in storage; upload not completed",
        )
    doc.size_bytes = minio_client.stat_size(doc.object_key, doc.bucket)
    doc.status = ProcessingStatus.PROCESSED
    doc.updated_at = utcnow()
    await doc.save()
    return doc


@router.get("/{landmarks_id}/download", response_model=PresignedDownload)
async def download_landmarks(
    landmarks_id: PydanticObjectId, _: User = Depends(get_current_user)
) -> PresignedDownload:
    doc = await BodyLandmarks.get(landmarks_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Landmarks not found")
    url = minio_client.presigned_get_url(doc.object_key, doc.bucket)
    return PresignedDownload(
        bucket=doc.bucket,
        object_key=doc.object_key,
        download_url=url,
        expires_in=settings.MINIO_PRESIGN_EXPIRY,
    )
