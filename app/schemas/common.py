"""Shared response schemas."""

from datetime import datetime

from pydantic import BaseModel


class PresignedUpload(BaseModel):
    """Returned when a client requests to upload a binary to MinIO."""

    bucket: str
    object_key: str
    upload_url: str
    expires_in: int


class PresignedDownload(BaseModel):
    bucket: str
    object_key: str
    download_url: str
    expires_in: int
    expires_at: datetime | None = None


class Message(BaseModel):
    detail: str
