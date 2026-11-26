"""Local speech-to-text with faster-whisper (OpenAI Whisper weights)."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("nilo.transcription")

_model = None
_model_lock = threading.Lock()
_warmup_done = False


class TranscriptionError(RuntimeError):
    """Audio could not be transcribed."""


def _extension_from_name(name: str | None, *, default: str = ".webm") -> str:
    if not name:
        return default
    ext = Path(name).suffix.lower()
    return ext if ext else default


def _prepare_wav_path(audio_bytes: bytes, source_ext: str) -> tuple[str, list[str]]:
    """Write bytes to disk and convert to 16 kHz mono WAV for Whisper."""
    source_ext = source_ext if source_ext.startswith(".") else f".{source_ext}"
    temp_paths: list[str] = []
    with tempfile.NamedTemporaryFile(suffix=source_ext, delete=False) as src:
        src.write(audio_bytes)
        src_path = src.name
    temp_paths.append(src_path)
    wav_path = f"{src_path}.whisper.wav"
    temp_paths.append(wav_path)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                src_path,
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "wav",
                wav_path,
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise TranscriptionError("ffmpeg not installed on server") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode(errors="replace")[-500:]
        raise TranscriptionError(f"ffmpeg failed: {stderr}") from exc
    return wav_path, temp_paths


def _cleanup_temp(paths: list[str]) -> None:
    for path in paths:
        try:
            os.unlink(path)
        except OSError:
            pass


def _get_whisper_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        if not settings.TRANSCRIPTION_ENABLED:
            raise TranscriptionError("Transcription is disabled")
        from faster_whisper import WhisperModel

        logger.info(
            "Loading Whisper model '%s' (device=%s)",
            settings.WHISPER_MODEL,
            settings.WHISPER_DEVICE,
        )
        try:
            _model = WhisperModel(
                settings.WHISPER_MODEL,
                device=settings.WHISPER_DEVICE,
                compute_type=settings.WHISPER_COMPUTE_TYPE,
            )
        except Exception as exc:  # noqa: BLE001
            raise TranscriptionError(f"Cannot load Whisper model: {exc}") from exc
        return _model


def warmup_whisper_model() -> None:
    """Download (if needed) and load Whisper weights into memory."""
    global _warmup_done
    if _warmup_done:
        return
    if not settings.TRANSCRIPTION_ENABLED:
        _warmup_done = True
        logger.info("Transcription disabled; skipping Whisper warmup")
        return
    if not settings.WHISPER_WARMUP_ON_STARTUP:
        _warmup_done = True
        logger.info("WHISPER_WARMUP_ON_STARTUP=false; lazy load on first request")
        return
    started = time.perf_counter()
    _get_whisper_model()
    _warmup_done = True
    elapsed = time.perf_counter() - started
    logger.info(
        "Whisper model '%s' ready (%.1fs)",
        settings.WHISPER_MODEL,
        elapsed,
    )


def is_transcription_ready() -> bool:
    if not settings.TRANSCRIPTION_ENABLED:
        return True
    if not settings.WHISPER_WARMUP_ON_STARTUP:
        return True
    return _model is not None


def transcribe_audio_bytes(
    audio_bytes: bytes,
    *,
    source_filename: str | None = None,
    language: str | None = None,
) -> tuple[str, str | None]:
    """Return ``(text, detected_language)``."""
    if not audio_bytes:
        raise TranscriptionError("Empty audio payload")
    ext = _extension_from_name(source_filename)
    wav_path, temps = _prepare_wav_path(audio_bytes, ext)
    try:
        model = _get_whisper_model()
        lang = language or settings.WHISPER_LANGUAGE or None
        if lang == "":
            lang = None
        try:
            # VAD off en clips cortos: evita falsos “sin voz” en notas de 2–5 s.
            use_vad = len(audio_bytes) > 48_000
            segments, info = model.transcribe(
                wav_path,
                language=lang,
                vad_filter=use_vad,
                beam_size=5,
            )
            parts = [seg.text.strip() for seg in segments if seg.text.strip()]
        except Exception as exc:  # noqa: BLE001
            raise TranscriptionError(f"Whisper inference failed: {exc}") from exc
        text = " ".join(parts).strip()
        detected = getattr(info, "language", None)
        if not text:
            raise TranscriptionError("No speech detected in audio")
        return text, detected
    finally:
        _cleanup_temp(temps)