"""MinIO object storage client and helpers.

The capture agent uploads binaries (video, audio, landmarks, documents)
directly to MinIO using presigned URLs, so FastAPI never proxies large
payloads. This module centralizes client creation, bucket bootstrap and
object-key conventions.
"""

import logging
from datetime import datetime, timedelta, timezone
from io import BytesIO

from minio import Minio
from minio.sseconfig import Rule, SSEConfig

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Minio | None = None
_presign_client: Minio | None = None


def _build_minio_client(endpoint: str, *, secure: bool | None = None) -> Minio:
    use_tls = settings.MINIO_SECURE if secure is None else secure
    return Minio(
        endpoint,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=use_tls,
    )


def get_minio() -> Minio:
    """Internal client (API container → MinIO on the Docker network)."""
    global _client
    if _client is None:
        _client = _build_minio_client(settings.MINIO_ENDPOINT)
    return _client


def get_presign_minio() -> Minio:
    """Client used to mint presigned URLs reachable from external agents."""
    global _presign_client
    if _presign_client is None:
        endpoint = settings.MINIO_PUBLIC_ENDPOINT or settings.MINIO_ENDPOINT
        _presign_client = _build_minio_client(
            endpoint, secure=settings.minio_presign_secure()
        )
    return _presign_client


def ensure_bucket(bucket: str | None = None) -> None:
    """Create the target bucket if it does not exist.

    When ``MINIO_SSE`` is enabled, set SSE-S3 as the bucket's default
    encryption so every object (including those uploaded via presigned URLs)
    is encrypted at rest. Requires a KMS configured on the MinIO server.
    """
    bucket = bucket or settings.MINIO_BUCKET
    client = get_minio()
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("Created MinIO bucket '%s'", bucket)
    if settings.MINIO_SSE:
        try:
            client.set_bucket_encryption(
                bucket, SSEConfig(Rule.new_sse_s3_rule())
            )
            logger.info("Enabled SSE-S3 default encryption on '%s'", bucket)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not enable SSE on bucket '%s' (is a KMS configured on "
                "MinIO?): %s",
                bucket,
                exc,
            )


def _slug_date(ts: datetime | None = None) -> str:
    """Date folder: día-mes-año (UTC)."""
    ts = ts or datetime.now(timezone.utc)
    return ts.strftime("%d-%m-%Y")


# Modalities under ``patients/<pid>/sessions/<sid>/``.
MODALITY_AUDIO = "audio"
MODALITY_AUDIO_NOTES = "audio_notes"
MODALITY_FACE_LANDMARKS = "face_landmarks"
MODALITY_POSE = "pose"
MODALITY_VIDEO = "video"


def landmarks_modality(capture_kind: str) -> str:
    """Map capture kind to storage folder under the session."""
    if capture_kind == "face":
        return MODALITY_FACE_LANDMARKS
    return MODALITY_POSE


def build_object_key(
    *,
    patient_id: str,
    session_id: str,
    modality: str,
    filename: str,
    ts: datetime | None = None,
) -> str:
    """Build a session-scoped object key.

    Example::

        patients/<pid>/sessions/<sid>/pose/24-11-2026/landmarks_1730000_mediapipe.json
    """
    date_part = _slug_date(ts)
    sid = session_id.strip("/")
    return (
        f"patients/{patient_id}/sessions/{sid}/{modality}/{date_part}/{filename}"
    )


def build_patient_document_key(
    *,
    patient_id: str,
    doc_type: str,
    filename: str,
    ts: datetime | None = None,
) -> str:
    """Non-session clinical documents (PDF, informes…)."""
    return f"patients/{patient_id}/documents/{doc_type}/{_slug_date(ts)}/{filename}"


def presigned_put_url(
    object_key: str,
    bucket: str | None = None,
    expiry_seconds: int | None = None,
) -> str:
    """Return a presigned URL the agent can use to PUT (upload) an object."""
    bucket = bucket or settings.MINIO_BUCKET
    expiry = expiry_seconds or settings.MINIO_PRESIGN_EXPIRY
    return get_presign_minio().presigned_put_object(
        bucket, object_key, expires=timedelta(seconds=expiry)
    )


def presigned_get_url(
    object_key: str,
    bucket: str | None = None,
    expiry_seconds: int | None = None,
) -> str:
    """Return a presigned URL to GET (download) an object."""
    bucket = bucket or settings.MINIO_BUCKET
    expiry = expiry_seconds or settings.MINIO_DOWNLOAD_EXPIRY
    return get_presign_minio().presigned_get_object(
        bucket, object_key, expires=timedelta(seconds=expiry)
    )


def put_object_bytes(
    object_key: str,
    data: bytes,
    *,
    bucket: str | None = None,
    content_type: str | None = None,
) -> int:
    """Server-side upload (API → MinIO), same credentials as mc."""
    bucket = bucket or settings.MINIO_BUCKET
    ensure_bucket()
    client = get_minio()
    length = len(data)
    client.put_object(
        bucket,
        object_key,
        BytesIO(data),
        length,
        content_type=content_type or "application/octet-stream",
    )
    return length


def delete_object(object_key: str, bucket: str | None = None) -> None:
    """Remove object from MinIO; no-op if missing (idempotent clinical delete)."""
    if not object_key:
        return
    bucket = bucket or settings.MINIO_BUCKET
    if not object_exists(object_key, bucket):
        logger.warning("MinIO delete skipped (not found): %s", object_key)
        return
    try:
        get_minio().remove_object(bucket, object_key)
    except Exception as exc:  # noqa: BLE001
        if object_exists(object_key, bucket):
            logger.error("MinIO delete failed for %s: %s", object_key, exc)
            raise
        logger.warning("MinIO delete raced/missing: %s", object_key)


def object_exists(object_key: str, bucket: str | None = None) -> bool:
    bucket = bucket or settings.MINIO_BUCKET
    try:
        get_minio().stat_object(bucket, object_key)
        return True
    except Exception:  # noqa: BLE001 - minio raises S3Error, treat as missing
        return False


def open_object(object_key: str, bucket: str | None = None):
    """Return a streaming GET response (caller must close / release)."""
    bucket = bucket or settings.MINIO_BUCKET
    return get_minio().get_object(bucket, object_key)


def get_object_bytes(object_key: str, bucket: str | None = None) -> bytes:
    response = open_object(object_key, bucket)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def stat_size(object_key: str, bucket: str | None = None) -> int | None:
    bucket = bucket or settings.MINIO_BUCKET
    try:
        return get_minio().stat_object(bucket, object_key).size
    except Exception:  # noqa: BLE001
        return None
