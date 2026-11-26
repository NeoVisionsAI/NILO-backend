"""Stream MinIO objects through the API (fallback when presign is blocked)."""

import mimetypes

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse

from app.storage import minio_client


def _guess_media_type(object_key: str) -> str:
    guessed, _ = mimetypes.guess_type(object_key)
    return guessed or "application/octet-stream"


def streaming_response_for_object(
    bucket: str, object_key: str
) -> StreamingResponse:
    if not minio_client.object_exists(object_key, bucket):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Object not found in storage",
        )
    response = minio_client.open_object(object_key, bucket)

    def _iter():
        try:
            yield from response.stream(amt=256 * 1024)
        finally:
            response.close()
            response.release_conn()

    return StreamingResponse(
        _iter(),
        media_type=_guess_media_type(object_key),
        headers={"Cache-Control": "private, no-store"},
    )