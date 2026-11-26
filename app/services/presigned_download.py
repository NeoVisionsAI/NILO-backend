"""Mint and reuse presigned GET URLs for clinical media (short-lived, cacheable)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.schemas.common import PresignedDownload
from app.storage import minio_client

_RENEW_BUFFER_SECONDS = 30
_cache_lock = threading.Lock()
_cache: dict[str, _CacheEntry] = {}


@dataclass
class _CacheEntry:
    download_url: str
    expires_at: datetime
    expires_in: int


def clamp_expiry_seconds(expiry_seconds: int | None, *, default: int | None = None) -> int:
    """Clamp TTL for presigned GET (60 s … 7 d)."""
    base = expiry_seconds if expiry_seconds is not None else (
        default if default is not None else settings.MINIO_VIEW_EXPIRY
    )
    return min(max(int(base), 60), 604_800)


def _cache_key(bucket: str, object_key: str, expiry_seconds: int) -> str:
    return f"{bucket}|{object_key}|{expiry_seconds}"


def mint_presigned_download(
    *,
    bucket: str,
    object_key: str,
    expiry_seconds: int | None = None,
    default_expiry: int | None = None,
) -> PresignedDownload:
    """Return a browser-reachable GET URL; reuse cached URL until it expires."""
    expiry = clamp_expiry_seconds(expiry_seconds, default=default_expiry)
    key = _cache_key(bucket, object_key, expiry)
    now = datetime.now(timezone.utc)

    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None and hit.expires_at > now + timedelta(
            seconds=_RENEW_BUFFER_SECONDS
        ):
            remaining = max(
                60,
                int((hit.expires_at - now).total_seconds()),
            )
            return PresignedDownload(
                bucket=bucket,
                object_key=object_key,
                download_url=hit.download_url,
                expires_in=remaining,
                expires_at=hit.expires_at,
            )

    url = minio_client.presigned_get_url(
        object_key, bucket, expiry_seconds=expiry
    )
    expires_at = now + timedelta(seconds=expiry)
    with _cache_lock:
        _cache[key] = _CacheEntry(
            download_url=url, expires_at=expires_at, expires_in=expiry
        )

    return PresignedDownload(
        bucket=bucket,
        object_key=object_key,
        download_url=url,
        expires_in=expiry,
        expires_at=expires_at,
    )