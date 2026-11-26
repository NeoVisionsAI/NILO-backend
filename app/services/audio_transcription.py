"""Persist Whisper transcription on ``AudioRecording`` documents."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from beanie import PydanticObjectId

from app.core.config import settings
from app.models.audio import AudioRecording
from app.models.base import utcnow
from app.models.enums import ProcessingStatus, TranscriptionStatus
from app.services.speech_transcription import TranscriptionError, transcribe_audio_bytes
from app.storage import minio_client

logger = logging.getLogger("nilo.audio_transcription")


def _guess_filename(object_key: str, fmt: str | None) -> str:
    suffix = Path(object_key).suffix
    if suffix:
        return f"audio{suffix}"
    if fmt:
        return f"audio.{fmt.lstrip('.')}"
    return "audio.webm"


async def transcribe_recording(
    audio_id: PydanticObjectId,
    *,
    force: bool = False,
    language: str | None = None,
) -> AudioRecording:
    audio = await AudioRecording.get(audio_id)
    if audio is None:
        raise LookupError("Audio not found")
    if not settings.TRANSCRIPTION_ENABLED:
        raise TranscriptionError("Transcription is disabled")

    if (
        audio.transcription_status == TranscriptionStatus.DONE
        and audio.transcription
        and not force
    ):
        return audio

    if audio.status == ProcessingStatus.PENDING_UPLOAD:
        raise TranscriptionError("Audio upload not completed")

    if (
        audio.duration_seconds is not None
        and audio.duration_seconds > settings.TRANSCRIPTION_MAX_AUDIO_SECONDS
    ):
        raise TranscriptionError("Audio exceeds maximum transcription length")

    if not minio_client.object_exists(audio.object_key, audio.bucket):
        raise TranscriptionError("Audio file missing in storage")

    data = minio_client.get_object_bytes(audio.object_key, audio.bucket)
    filename = _guess_filename(audio.object_key, audio.format)

    try:
        text, _detected = await asyncio.to_thread(
            transcribe_audio_bytes,
            data,
            source_filename=filename,
            language=language,
        )
    except TranscriptionError:
        audio.transcription_status = TranscriptionStatus.FAILED
        audio.updated_at = utcnow()
        await audio.save()
        raise

    audio.transcription = text
    audio.transcription_status = TranscriptionStatus.DONE
    audio.updated_at = utcnow()
    await audio.save()
    logger.info("Transcribed audio %s (%d chars)", audio_id, len(text))
    return audio


async def transcribe_recording_background(audio_id: PydanticObjectId) -> None:
    try:
        await transcribe_recording(audio_id, force=False)
    except LookupError:
        logger.warning("Background transcribe: audio %s not found", audio_id)
    except TranscriptionError as exc:
        logger.warning("Background transcribe failed for %s: %s", audio_id, exc)
    except Exception:  # noqa: BLE001
        logger.exception("Background transcribe unexpected error for %s", audio_id)