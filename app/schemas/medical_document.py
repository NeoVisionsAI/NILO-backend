"""Medical document schemas."""

from datetime import datetime

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict

from app.models.enums import DocumentType, ProcessingStatus


class MedicalDocumentUploadRequest(BaseModel):
    patient_id: PydanticObjectId
    doc_type: DocumentType = DocumentType.OTHER
    title: str
    description: str | None = None
    document_date: datetime | None = None
    content_type: str | None = None
    file_extension: str = "pdf"


class MedicalDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    patient_id: PydanticObjectId
    doc_type: DocumentType
    title: str
    description: str | None = None
    document_date: datetime | None = None
    bucket: str
    object_key: str
    size_bytes: int | None = None
    content_type: str | None = None
    status: ProcessingStatus
