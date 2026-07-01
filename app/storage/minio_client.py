"""MinIO object storage client and helpers.

The capture agent uploads binaries (video, audio, landmarks, documents)
directly to MinIO using presigned URLs, so FastAPI never proxies large
payloads. This module centralizes client creation, bucket bootstrap and
object-key conventions.
"""

import logging
from datetime import datetime, timedelta, timezone

from minio import Minio
from minio.sseconfig import Rule, SSEConfig

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Minio | None = None


def get_minio() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
    return _client


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
    ts = ts or datetime.now(timezone.utc)
    return ts.strftime("%Y-%m-%d")


def build_object_key(
    patient_id: str,
    category: str,
    filename: str,
    ts: datetime | None = None,
    subpath: str | None = None,
) -> str:
    """Build a structured object key.

    Example: ``patients/<pid>/video/2026-07-01/<session>/000001_start.mp4``
    """
    parts = ["patients", patient_id, category, _slug_date(ts)]
    if subpath:
        parts.append(subpath.strip("/"))
    parts.append(filename)
    return "/".join(parts)


def presigned_put_url(
    object_key: str,
    bucket: str | None = None,
    expiry_seconds: int | None = None,
) -> str:
    """Return a presigned URL the agent can use to PUT (upload) an object."""
    bucket = bucket or settings.MINIO_BUCKET
    expiry = expiry_seconds or settings.MINIO_PRESIGN_EXPIRY
    return get_minio().presigned_put_object(
        bucket, object_key, expires=timedelta(seconds=expiry)
    )


def presigned_get_url(
    object_key: str,
    bucket: str | None = None,
    expiry_seconds: int | None = None,
) -> str:
    """Return a presigned URL to GET (download) an object."""
    bucket = bucket or settings.MINIO_BUCKET
    expiry = expiry_seconds or settings.MINIO_PRESIGN_EXPIRY
    return get_minio().presigned_get_object(
        bucket, object_key, expires=timedelta(seconds=expiry)
    )


def object_exists(object_key: str, bucket: str | None = None) -> bool:
    bucket = bucket or settings.MINIO_BUCKET
    try:
        get_minio().stat_object(bucket, object_key)
        return True
    except Exception:  # noqa: BLE001 - minio raises S3Error, treat as missing
        return False


def stat_size(object_key: str, bucket: str | None = None) -> int | None:
    bucket = bucket or settings.MINIO_BUCKET
    try:
        return get_minio().stat_object(bucket, object_key).size
    except Exception:  # noqa: BLE001
        return None
