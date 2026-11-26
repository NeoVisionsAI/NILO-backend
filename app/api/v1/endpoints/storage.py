"""Unified temporary MinIO read access (presigned GET + cache)."""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.common import PresignedDownload
from app.services.presigned_download import mint_presigned_download
from app.services.storage_resolver import StorageResourceKind, resolve_storage_object

router = APIRouter()


@router.get("/access", response_model=PresignedDownload)
async def storage_access(
    kind: StorageResourceKind,
    resource_id: PydanticObjectId,
    expires_in: int | None = None,
    _: User = Depends(get_current_user),
) -> PresignedDownload:
    """Mint (or reuse) a presigned GET for one stored object.

    Same object + TTL within the validity window returns the cached URL.
    ``expires_in`` seconds (default ``MINIO_VIEW_EXPIRY``, min 60, max 7 d).
    """
    bucket, object_key = await resolve_storage_object(kind, resource_id)
    return mint_presigned_download(
        bucket=bucket, object_key=object_key, expiry_seconds=expires_in
    )