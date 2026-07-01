"""Medical document endpoints (reports, lab results, imaging...).

Placeholder domain for the future. Files are uploaded to MinIO via presigned
URL and associated to a patient.
"""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_staff
from app.core.config import settings
from app.models.base import utcnow
from app.models.enums import ProcessingStatus
from app.models.medical_document import MedicalDocument
from app.models.user import User
from app.schemas.common import PresignedDownload
from app.schemas.medical_document import (
    MedicalDocumentOut,
    MedicalDocumentUploadRequest,
)
from app.storage import minio_client

router = APIRouter()


class _DocumentUploadResponse(MedicalDocumentOut):
    upload_url: str
    upload_expires_in: int


@router.post(
    "",
    response_model=_DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_document_upload(
    payload: MedicalDocumentUploadRequest,
    current_user: User = Depends(require_staff),
) -> _DocumentUploadResponse:
    safe_title = payload.title.lower().replace(" ", "_")[:50]
    filename = f"{safe_title}.{payload.file_extension}"
    object_key = minio_client.build_object_key(
        patient_id=str(payload.patient_id),
        category="documents",
        filename=filename,
        ts=payload.document_date,
        subpath=payload.doc_type.value,
    )
    doc = MedicalDocument(
        patient_id=payload.patient_id,
        doc_type=payload.doc_type,
        title=payload.title,
        description=payload.description,
        document_date=payload.document_date,
        bucket=settings.MINIO_BUCKET,
        object_key=object_key,
        content_type=payload.content_type,
        status=ProcessingStatus.PENDING_UPLOAD,
        uploaded_by=current_user.id,
    )
    await doc.insert()
    upload_url = minio_client.presigned_put_url(object_key)
    return _DocumentUploadResponse(
        **MedicalDocumentOut.model_validate(doc).model_dump(),
        upload_url=upload_url,
        upload_expires_in=settings.MINIO_PRESIGN_EXPIRY,
    )


@router.get("", response_model=list[MedicalDocumentOut])
async def list_documents(
    patient_id: PydanticObjectId,
    skip: int = 0,
    limit: int = 200,
    _: User = Depends(get_current_user),
) -> list[MedicalDocument]:
    return (
        await MedicalDocument.find(MedicalDocument.patient_id == patient_id)
        .sort(-MedicalDocument.created_at)
        .skip(skip)
        .limit(limit)
        .to_list()
    )


@router.get("/{document_id}", response_model=MedicalDocumentOut)
async def get_document(
    document_id: PydanticObjectId, _: User = Depends(get_current_user)
) -> MedicalDocument:
    doc = await MedicalDocument.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/{document_id}/confirm", response_model=MedicalDocumentOut)
async def confirm_document_upload(
    document_id: PydanticObjectId, _: User = Depends(require_staff)
) -> MedicalDocument:
    doc = await MedicalDocument.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not minio_client.object_exists(doc.object_key, doc.bucket):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Object not found in storage; upload not completed",
        )
    doc.size_bytes = minio_client.stat_size(doc.object_key, doc.bucket)
    doc.status = ProcessingStatus.UPLOADED
    doc.updated_at = utcnow()
    await doc.save()
    return doc


@router.get("/{document_id}/download", response_model=PresignedDownload)
async def download_document(
    document_id: PydanticObjectId, _: User = Depends(get_current_user)
) -> PresignedDownload:
    doc = await MedicalDocument.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    url = minio_client.presigned_get_url(doc.object_key, doc.bucket)
    return PresignedDownload(
        bucket=doc.bucket,
        object_key=doc.object_key,
        download_url=url,
        expires_in=settings.MINIO_PRESIGN_EXPIRY,
    )
