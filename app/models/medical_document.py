"""Medical documents (reports, lab results, imaging...).

Placeholder domain for the future: files are stored in MinIO and metadata is
kept here, associated to a patient.
"""

from datetime import datetime

from beanie import Document, Indexed, PydanticObjectId

from app.models.base import TimestampMixin
from app.models.enums import DocumentType, ProcessingStatus


class MedicalDocument(Document, TimestampMixin):
    patient_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]
    doc_type: DocumentType = DocumentType.OTHER
    title: str
    description: str | None = None

    # Document instant (e.g. the date of the report / analysis).
    document_date: datetime | None = None

    bucket: str
    object_key: str
    size_bytes: int | None = None
    content_type: str | None = None

    status: ProcessingStatus = ProcessingStatus.PENDING_UPLOAD
    uploaded_by: PydanticObjectId | None = None

    class Settings:
        name = "medical_documents"
