"""Body landmarks endpoints (MediaPipe / YOLO).

Landmark payloads (per-frame keypoints) are uploaded to MinIO via presigned
URL; this document keeps the metadata and a link to the source video segment.
"""

from datetime import datetime
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user, require_staff
from app.core.config import settings
from app.core.upload_body import read_landmarks_upload_bytes
from app.models.base import utcnow
from app.models.enums import LandmarkCaptureKind, LandmarkSource, ProcessingStatus
from app.models.landmarks import BodyLandmarks
from app.models.user import User
from app.schemas.common import PresignedDownload
from app.services.media_stream import streaming_response_for_object
from app.services.presigned_download import mint_presigned_download
from app.schemas.landmarks import LandmarksOut, LandmarksUploadRequest
from app.services.clinical_delete import delete_landmarks_record
from app.services.monitoring_session import require_active_ingestion
from app.storage import minio_client

router = APIRouter()


class _LandmarksUploadResponse(LandmarksOut):
    upload_url: str
    upload_expires_in: int


@router.post(
    "/upload",
    response_model=LandmarksOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload landmarks file via API (multipart)",
    description=(
        "Multipart: form fields + `file` (JSON, gzip `.json.gz`, or **zip** with one `.json`). "
        "API extracts JSON and stores plain JSON in MinIO. Max after decompress: 64 MiB. "
        "Front: `schema: nilo-mediapipe-face-capture-v1`, `landmark_encoding: flat-xyz`. "
        "Preferred: zip with `landmarks.json` inside. nginx: `client_max_body_size 64m`."
    ),
)
async def upload_landmarks_body(
    session_id: Annotated[PydanticObjectId, Form()],
    patient_id: Annotated[PydanticObjectId, Form()],
    start_ts: Annotated[datetime, Form(description="ISO-8601")],
    file: UploadFile = File(
        ...,
        description="JSON, gzip (.json.gz), or zip containing one landmarks .json",
    ),
    source: LandmarkSource = Form(LandmarkSource.MEDIAPIPE),
    capture_kind: LandmarkCaptureKind = Form(
        LandmarkCaptureKind.FACE,
        description="face → MinIO face_landmarks/; pose → pose/ (cuerpo)",
    ),
    node_id: Annotated[PydanticObjectId | None, Form()] = None,
    video_segment_id: Annotated[PydanticObjectId | None, Form()] = None,
    model_name: Annotated[str | None, Form()] = None,
    end_ts: Annotated[datetime | None, Form()] = None,
    frame_count: Annotated[int | None, Form()] = None,
    file_extension: Annotated[
        str, Form(description="Storage extension, default json (use json if gzip wire)")
    ] = "json",
    _: User = Depends(require_staff),
) -> BodyLandmarks:
    """Multipart upload: API writes to MinIO (no browser presigned PUT)."""
    await require_active_ingestion(
        session_id=session_id,
        patient_id=patient_id,
        node_id=node_id,
    )
    data = await read_landmarks_upload_bytes(file)
    store_ext = "json"
    if file_extension and file_extension.lower() not in ("gz", "gzip", "zip"):
        store_ext = file_extension.lstrip(".")
    filename = f"landmarks_{int(start_ts.timestamp())}_{source.value}.{store_ext}"
    modality = minio_client.landmarks_modality(capture_kind.value)
    object_key = minio_client.build_object_key(
        patient_id=str(patient_id),
        session_id=str(session_id),
        modality=modality,
        filename=filename,
        ts=start_ts,
    )
    content_type = "application/json"
    size = minio_client.put_object_bytes(object_key, data, content_type=content_type)
    doc = BodyLandmarks(
        session_id=session_id,
        patient_id=patient_id,
        node_id=node_id,
        video_segment_id=video_segment_id,
        source=source,
        capture_kind=capture_kind,
        model_name=model_name,
        start_ts=start_ts,
        end_ts=end_ts,
        frame_count=frame_count,
        bucket=settings.MINIO_BUCKET,
        object_key=object_key,
        size_bytes=size,
        status=ProcessingStatus.PROCESSED,
    )
    await doc.insert()
    return doc


@router.post(
    "",
    response_model=_LandmarksUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_landmarks_upload(
    payload: LandmarksUploadRequest, _: User = Depends(require_staff)
) -> _LandmarksUploadResponse:
    await require_active_ingestion(
        session_id=payload.session_id,
        patient_id=payload.patient_id,
        node_id=payload.node_id,
    )
    filename = f"landmarks_{int(payload.start_ts.timestamp())}_{payload.source.value}.{payload.file_extension}"
    modality = minio_client.landmarks_modality(payload.capture_kind.value)
    object_key = minio_client.build_object_key(
        patient_id=str(payload.patient_id),
        session_id=str(payload.session_id),
        modality=modality,
        filename=filename,
        ts=payload.start_ts,
    )
    doc = BodyLandmarks(
        session_id=payload.session_id,
        patient_id=payload.patient_id,
        node_id=payload.node_id,
        video_segment_id=payload.video_segment_id,
        source=payload.source,
        capture_kind=payload.capture_kind,
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
    session_id: PydanticObjectId | None = None,
    node_id: PydanticObjectId | None = None,
    capture_kind: LandmarkCaptureKind | None = None,
    storage_ready: bool = True,
    skip: int = 0,
    limit: int = 200,
    _: User = Depends(get_current_user),
) -> list[BodyLandmarks]:
    """List landmark batches. Default: only rows with an object present in MinIO."""
    conditions = [BodyLandmarks.patient_id == patient_id]
    if session_id is not None:
        conditions.append(BodyLandmarks.session_id == session_id)
    if node_id is not None:
        conditions.append(BodyLandmarks.node_id == node_id)
    if capture_kind is not None:
        conditions.append(BodyLandmarks.capture_kind == capture_kind)
    rows = (
        await BodyLandmarks.find(*conditions)
        .sort(-BodyLandmarks.start_ts)
        .skip(skip)
        .limit(limit)
        .to_list()
    )
    if not storage_ready:
        return rows
    ready: list[BodyLandmarks] = []
    for doc in rows:
        if doc.status == ProcessingStatus.PENDING_UPLOAD:
            continue
        if minio_client.object_exists(doc.object_key, doc.bucket):
            ready.append(doc)
    return ready


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
    landmarks_id: PydanticObjectId,
    expires_in: int | None = None,
    _: User = Depends(get_current_user),
) -> PresignedDownload:
    doc = await BodyLandmarks.get(landmarks_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Landmarks not found")
    if doc.status == ProcessingStatus.PENDING_UPLOAD:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Upload not completed",
        )
    return mint_presigned_download(
        bucket=doc.bucket,
        object_key=doc.object_key,
        expiry_seconds=expires_in,
    )


@router.get("/{landmarks_id}/file")
async def landmarks_file(
    landmarks_id: PydanticObjectId,
    _: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream JSON (or gzip) from MinIO via API — no presign / CORS."""
    doc = await BodyLandmarks.get(landmarks_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Landmarks not found")
    if not minio_client.object_exists(doc.object_key, doc.bucket):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Object not found in storage; the batch may be from an incomplete "
                "presign upload. Re-capture or delete the Mongo row."
            ),
        )
    return streaming_response_for_object(doc.bucket, doc.object_key)


@router.delete(
    "/{landmarks_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_landmarks(
    landmarks_id: PydanticObjectId, _: User = Depends(require_staff)
) -> Response:
    doc = await BodyLandmarks.get(landmarks_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Landmarks not found")
    await delete_landmarks_record(doc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
