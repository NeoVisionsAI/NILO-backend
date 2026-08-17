"""Helpers for handling base64 photos stored in the database.

Photos are kept as base64 data URIs inside the owning document (encrypted at
rest), never as physical files.
"""

import base64

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

# Accepted image content types for uploads.
ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def validate_photo_data_uri(photo: str | None) -> None:
    """Reject a base64 photo whose decoded size exceeds the configured limit."""
    if not photo:
        return
    b64 = photo
    if b64.startswith("data:"):
        comma = b64.find(",")
        if comma != -1:
            b64 = b64[comma + 1 :]
    approx_bytes = (len(b64) * 3) // 4
    if approx_bytes > settings.MAX_PHOTO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Photo exceeds {settings.MAX_PHOTO_BYTES} bytes",
        )


async def upload_to_data_uri(file: UploadFile) -> str:
    """Validate an uploaded image and return it as a base64 data URI."""
    content_type = file.content_type or ""
    if content_type not in ALLOWED_PHOTO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported image type (allowed: jpeg, png, webp, gif)",
        )
    content = await file.read()
    if len(content) > settings.MAX_PHOTO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Photo exceeds {settings.MAX_PHOTO_BYTES} bytes",
        )
    b64 = base64.b64encode(content).decode("ascii")
    return f"data:{content_type};base64,{b64}"
