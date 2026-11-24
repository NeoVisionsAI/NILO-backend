"""Read multipart uploads with optional gzip and size limits."""

import gzip

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings


async def read_proxy_upload_bytes(file: UploadFile) -> bytes:
    """Read upload file; decompress gzip; enforce ``MAX_PROXY_UPLOAD_BYTES``."""
    raw = await file.read()
    if len(raw) > settings.MAX_PROXY_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Upload exceeds {settings.MAX_PROXY_UPLOAD_BYTES} bytes "
                f"({settings.MAX_PROXY_UPLOAD_BYTES // (1024 * 1024)} MiB). "
                "Use gzip on the client or raise nginx client_max_body_size."
            ),
        )
    name = (file.filename or "").lower()
    gz = name.endswith(".gz") or file.content_type in (
        "application/gzip",
        "application/x-gzip",
    )
    if not gz:
        return raw
    try:
        data = gzip.decompress(raw)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid gzip payload",
        ) from exc
    if len(data) > settings.MAX_PROXY_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Decompressed payload exceeds {settings.MAX_PROXY_UPLOAD_BYTES} bytes "
                f"({settings.MAX_PROXY_UPLOAD_BYTES // (1024 * 1024)} MiB)."
            ),
        )
    return data