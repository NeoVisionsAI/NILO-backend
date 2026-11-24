"""Read multipart uploads with optional gzip/zip and size limits."""

import gzip
import io
import zipfile

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings


def _detail_413(byte_count: int) -> str:
    max_b = settings.MAX_PROXY_UPLOAD_BYTES
    return (
        f"Payload exceeds {max_b} bytes ({max_b // (1024 * 1024)} MiB). "
        "Compress with zip/gzip or raise nginx client_max_body_size."
    )


def _extract_json_from_zip(raw: bytes) -> bytes:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid zip archive",
        ) from exc
    members = [
        name
        for name in zf.namelist()
        if not name.endswith("/") and name.lower().endswith(".json")
    ]
    if not members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zip must contain at least one .json file (face landmarks)",
        )
    name = next((n for n in members if "landmark" in n.lower()), members[0])
    total_uncompressed = sum(
        info.file_size for info in zf.infolist() if not info.is_dir()
    )
    if total_uncompressed > settings.MAX_PROXY_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=_detail_413(total_uncompressed),
        )
    try:
        data = zf.read(name)
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read JSON from zip",
        ) from exc
    if len(data) > settings.MAX_PROXY_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=_detail_413(len(data)),
        )
    return data


async def read_proxy_upload_bytes(file: UploadFile) -> bytes:
    """Read upload; optional gzip only (audio and generic)."""
    raw = await file.read()
    if len(raw) > settings.MAX_PROXY_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=_detail_413(len(raw)),
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
            detail=_detail_413(len(data)),
        )
    return data


async def read_landmarks_upload_bytes(file: UploadFile) -> bytes:
    """Landmarks: raw JSON, gzip (.json.gz), or zip with one .json inside."""
    raw = await file.read()
    if len(raw) > settings.MAX_PROXY_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=_detail_413(len(raw)),
        )
    name = (file.filename or "").lower()
    ctype = (file.content_type or "").lower()
    if name.endswith(".zip") or ctype in ("application/zip", "application/x-zip-compressed"):
        return _extract_json_from_zip(raw)
    if name.endswith(".gz") or ctype in ("application/gzip", "application/x-gzip"):
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
                detail=_detail_413(len(data)),
            )
        return data
    return raw