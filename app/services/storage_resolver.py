"""Resolve API resource kind + id to a MinIO object."""

from enum import StrEnum

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.models.audio import AudioRecording
from app.models.enums import ProcessingStatus
from app.models.landmarks import BodyLandmarks
from app.models.medical_document import MedicalDocument
from app.models.monitoring_session import VideoSegment
from app.models.pain_event import PainEvent
from app.storage import minio_client


class StorageResourceKind(StrEnum):
    LANDMARKS = "landmarks"
    AUDIO = "audio"
    VIDEO_SEGMENT = "video_segment"
    PAIN_EVENT = "pain_event"
    MEDICAL_DOCUMENT = "medical_document"


async def resolve_storage_object(
    kind: StorageResourceKind, resource_id: PydanticObjectId
) -> tuple[str, str]:
    """Return ``(bucket, object_key)`` or raise 404."""
    if kind == StorageResourceKind.LANDMARKS:
        doc = await BodyLandmarks.get(resource_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Landmarks not found")
        if doc.status == ProcessingStatus.PENDING_UPLOAD:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Upload not completed",
            )
        return doc.bucket, doc.object_key

    if kind == StorageResourceKind.AUDIO:
        audio = await AudioRecording.get(resource_id)
        if audio is None:
            raise HTTPException(status_code=404, detail="Audio not found")
        return audio.bucket, audio.object_key

    if kind == StorageResourceKind.VIDEO_SEGMENT:
        seg = await VideoSegment.get(resource_id)
        if seg is None:
            raise HTTPException(status_code=404, detail="Video segment not found")
        return seg.bucket, seg.object_key

    if kind == StorageResourceKind.PAIN_EVENT:
        ev = await PainEvent.get(resource_id)
        if ev is None:
            raise HTTPException(status_code=404, detail="Pain event not found")
        if not ev.video_object_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pain event has no video object",
            )
        return ev.bucket, ev.video_object_key

    if kind == StorageResourceKind.MEDICAL_DOCUMENT:
        doc = await MedicalDocument.get(resource_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc.bucket, doc.object_key

    raise HTTPException(status_code=400, detail="Unknown resource kind")


async def require_object_ready(bucket: str, object_key: str) -> None:
    if not minio_client.object_exists(object_key, bucket):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Object not found in storage",
        )