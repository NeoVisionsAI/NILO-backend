"""Delete clinical records and optional MinIO binaries."""

from __future__ import annotations

import logging
from app.models.audio import AudioRecording
from app.models.landmarks import BodyLandmarks
from app.models.monitoring_session import VideoSegment
from app.models.pain_event import PainEvent
from app.models.physiological import PhysiologicalReading
from app.models.session_text_note import SessionTextNote
from app.storage import minio_client

logger = logging.getLogger("nilo.clinical_delete")


def delete_minio_keys(bucket: str, *object_keys: str | None) -> None:
    for key in object_keys:
        if key:
            try:
                minio_client.delete_object(key, bucket)
            except Exception:  # noqa: BLE001 — Mongo cleanup must proceed
                logger.warning("MinIO key not removed (continuing): %s", key)


async def delete_landmarks_record(doc: BodyLandmarks) -> None:
    delete_minio_keys(doc.bucket, doc.object_key)
    await doc.delete()


async def delete_audio_record(audio: AudioRecording) -> None:
    delete_minio_keys(audio.bucket, audio.object_key)
    await audio.delete()


async def delete_pain_event_record(event: PainEvent) -> None:
    delete_minio_keys(
        event.bucket,
        event.video_object_key,
        event.landmarks_object_key,
    )
    await event.delete()


async def delete_video_segment_record(segment: VideoSegment) -> None:
    delete_minio_keys(segment.bucket, segment.object_key)
    await segment.delete()


async def delete_text_note_record(note: SessionTextNote) -> None:
    await note.delete()


async def delete_physiological_record(reading: PhysiologicalReading) -> None:
    await reading.delete()