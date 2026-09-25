"""Monitoring session lifecycle and video segments within a session."""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_staff
from app.core.config import settings
from app.models.audio import AudioRecording
from app.models.base import utcnow
from app.models.enums import MonitoringSessionStatus, ProcessingStatus
from app.models.landmarks import BodyLandmarks
from app.models.monitoring_session import MonitoringSession, VideoSegment
from app.models.pain_event import PainEvent
from app.models.patient import Patient
from app.models.physiological import PhysiologicalReading
from app.models.user import User
from app.schemas.common import PresignedDownload, PresignedUpload
from app.schemas.monitoring_session import (
    MonitoringSessionCreate,
    MonitoringSessionOut,
    SegmentOut,
    SegmentUploadRequest,
    SegmentUploadResponse,
    SessionOverviewOut,
)
from app.services.monitoring_session import (
    count_session_documents,
    require_active_ingestion,
    require_node,
    require_session,
)
from app.storage import minio_client

router = APIRouter()


@router.post(
    "", response_model=MonitoringSessionOut, status_code=status.HTTP_201_CREATED
)
async def create_session(
    payload: MonitoringSessionCreate, _: User = Depends(require_staff)
) -> MonitoringSession:
    if payload.node_id is not None:
        await require_node(payload.node_id)
    patient = await Patient.get(payload.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    if (
        payload.node_id is not None
        and patient.node_id is not None
        and patient.node_id != payload.node_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="node_id does not match the patient's assigned node",
        )

    session = MonitoringSession(
        patient_id=payload.patient_id,
        node_id=payload.node_id,
        external_session_id=payload.external_session_id,
        archive_chunk_seconds=payload.archive_chunk_seconds
        or settings.DEFAULT_VIDEO_CHUNK_SECONDS,
        hls_segment_seconds=payload.hls_segment_seconds
        or settings.DEFAULT_HLS_SEGMENT_SECONDS,
    )
    await session.insert()
    return session


@router.get("", response_model=list[MonitoringSessionOut])
async def list_sessions(
    patient_id: PydanticObjectId | None = None,
    node_id: PydanticObjectId | None = None,
    status_filter: MonitoringSessionStatus | None = None,
    skip: int = 0,
    limit: int = 100,
    _: User = Depends(get_current_user),
) -> list[MonitoringSession]:
    filters = []
    if patient_id is not None:
        filters.append(MonitoringSession.patient_id == patient_id)
    if node_id is not None:
        filters.append(MonitoringSession.node_id == node_id)
    if status_filter is not None:
        filters.append(MonitoringSession.status == status_filter)
    query = (
        MonitoringSession.find(*filters)
        if filters
        else MonitoringSession.find_all()
    )
    return await query.sort(-MonitoringSession.started_at).skip(skip).limit(limit).to_list()


@router.get("/{session_id}", response_model=MonitoringSessionOut)
async def get_session(
    session_id: PydanticObjectId, _: User = Depends(get_current_user)
) -> MonitoringSession:
    return await require_session(session_id)


@router.get("/{session_id}/overview", response_model=SessionOverviewOut)
async def get_session_overview(
    session_id: PydanticObjectId, _: User = Depends(get_current_user)
) -> SessionOverviewOut:
    session = await require_session(session_id)
    return SessionOverviewOut(
        session=MonitoringSessionOut.model_validate(session),
        video_segments=await count_session_documents(VideoSegment, session_id),
        audio_clips=await count_session_documents(AudioRecording, session_id),
        physiological_readings=await count_session_documents(
            PhysiologicalReading, session_id
        ),
        landmarks_batches=await count_session_documents(BodyLandmarks, session_id),
        pain_events=await count_session_documents(PainEvent, session_id),
    )


@router.post("/{session_id}/end", response_model=MonitoringSessionOut)
async def end_session(
    session_id: PydanticObjectId, _: User = Depends(require_staff)
) -> MonitoringSession:
    session = await require_session(session_id, must_be_active=True)
    session.status = MonitoringSessionStatus.COMPLETED
    session.ended_at = utcnow()
    session.updated_at = utcnow()
    await session.save()
    return session


@router.post(
    "/{session_id}/video-segments",
    response_model=SegmentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_video_segment_upload(
    session_id: PydanticObjectId,
    payload: SegmentUploadRequest,
    _: User = Depends(require_staff),
) -> SegmentUploadResponse:
    session = await require_active_ingestion(
        session_id=session_id,
        node_id=payload.node_id,
    )

    filename = f"{payload.seq:06d}_{int(payload.start_ts.timestamp())}.{payload.file_extension}"
    object_key = minio_client.build_object_key(
        patient_id=str(session.patient_id),
        category="video",
        filename=filename,
        ts=payload.start_ts,
        subpath=str(session.id),
    )

    segment = VideoSegment(
        session_id=session.id,
        patient_id=session.patient_id,
        node_id=payload.node_id,
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


@router.get("/{session_id}/video-segments", response_model=list[SegmentOut])
async def list_video_segments(
    session_id: PydanticObjectId,
    skip: int = 0,
    limit: int = 500,
    _: User = Depends(get_current_user),
) -> list[VideoSegment]:
    await require_session(session_id)
    return (
        await VideoSegment.find(VideoSegment.session_id == session_id)
        .sort(+VideoSegment.seq)
        .skip(skip)
        .limit(limit)
        .to_list()
    )


@router.post("/video-segments/{segment_id}/confirm", response_model=SegmentOut)
async def confirm_video_segment_upload(
    segment_id: PydanticObjectId, _: User = Depends(require_staff)
) -> VideoSegment:
    segment = await VideoSegment.get(segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Video segment not found")
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
    "/video-segments/{segment_id}/download", response_model=PresignedDownload
)
async def download_video_segment(
    segment_id: PydanticObjectId, _: User = Depends(get_current_user)
) -> PresignedDownload:
    segment = await VideoSegment.get(segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Video segment not found")
    url = minio_client.presigned_get_url(segment.object_key, segment.bucket)
    return PresignedDownload(
        bucket=segment.bucket,
        object_key=segment.object_key,
        download_url=url,
        expires_in=settings.MINIO_PRESIGN_EXPIRY,
    )
