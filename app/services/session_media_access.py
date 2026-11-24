"""Batch mint presigned GET URLs for all uploaded media in a session."""

from datetime import datetime, timezone

from beanie import PydanticObjectId
from beanie.operators import In

from app.core.config import settings
from app.models.audio import AudioRecording
from app.models.enums import ProcessingStatus
from app.models.landmarks import BodyLandmarks
from app.models.monitoring_session import VideoSegment
from app.models.pain_event import PainEvent
from app.schemas.session_media import SessionMediaAccessOut, SessionMediaItem
from app.storage import minio_client

_READY_STATUSES = {
    ProcessingStatus.UPLOADED,
    ProcessingStatus.PROCESSING,
    ProcessingStatus.PROCESSED,
}


def _download_link(
    *,
    kind: str,
    resource_id: PydanticObjectId,
    object_key: str,
    bucket: str,
    expiry_seconds: int,
) -> SessionMediaItem:
    return SessionMediaItem(
        kind=kind,
        id=resource_id,
        bucket=bucket,
        object_key=object_key,
        download_url=minio_client.presigned_get_url(
            object_key, bucket, expiry_seconds=expiry_seconds
        ),
        expires_in=expiry_seconds,
    )


async def build_session_media_access(
    session_id: PydanticObjectId,
    *,
    expiry_seconds: int | None = None,
) -> SessionMediaAccessOut:
    """One round-trip presigned GET links for clinical review (renewable)."""
    expiry = expiry_seconds or settings.MINIO_DOWNLOAD_EXPIRY
    expiry = min(max(expiry, 60), 604_800)

    items: list[SessionMediaItem] = []

    segments = await VideoSegment.find(
        VideoSegment.session_id == session_id,
        VideoSegment.status == ProcessingStatus.UPLOADED,
    ).to_list()
    for seg in segments:
        items.append(
            _download_link(
                kind="video_segment",
                resource_id=seg.id,
                object_key=seg.object_key,
                bucket=seg.bucket,
                expiry_seconds=expiry,
            )
        )

    audio = await AudioRecording.find(
        AudioRecording.session_id == session_id,
        In(AudioRecording.status, list(_READY_STATUSES)),
    ).to_list()
    for clip in audio:
        items.append(
            _download_link(
                kind="audio",
                resource_id=clip.id,
                object_key=clip.object_key,
                bucket=clip.bucket,
                expiry_seconds=expiry,
            )
        )

    landmarks = await BodyLandmarks.find(
        BodyLandmarks.session_id == session_id,
    ).to_list()
    for doc in landmarks:
        if doc.status == ProcessingStatus.PENDING_UPLOAD:
            continue
        items.append(
            _download_link(
                kind="landmarks",
                resource_id=doc.id,
                object_key=doc.object_key,
                bucket=doc.bucket,
                expiry_seconds=expiry,
            )
        )

    events = await PainEvent.find(PainEvent.session_id == session_id).to_list()
    for ev in events:
        if ev.status == ProcessingStatus.PENDING_UPLOAD:
            continue
        if not ev.video_object_key:
            continue
        items.append(
            _download_link(
                kind="pain_event",
                resource_id=ev.id,
                object_key=ev.video_object_key,
                bucket=ev.bucket,
                expiry_seconds=expiry,
            )
        )

    return SessionMediaAccessOut(
        session_id=session_id,
        expires_in=expiry,
        generated_at=datetime.now(timezone.utc),
        items=items,
    )