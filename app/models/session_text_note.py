"""Free-text clinical notes attached to a monitoring session.

Stored in MongoDB (no MinIO). Body is encrypted at rest like other PII.
"""

from datetime import datetime

from beanie import Document, Indexed, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.base import TimestampMixin, utcnow
from app.models.fields import ENCRYPTED_BSON_ENCODERS, EncryptedStr


class SessionTextNote(Document, TimestampMixin):
    session_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]
    patient_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]
    node_id: PydanticObjectId | None = None
    body: EncryptedStr
    recorded_at: datetime = Field(default_factory=utcnow)
    author_id: PydanticObjectId | None = None

    class Settings:
        name = "session_text_notes"
        bson_encoders = ENCRYPTED_BSON_ENCODERS
        validate_on_save = True
        indexes = [
            IndexModel([("session_id", ASCENDING), ("recorded_at", DESCENDING)]),
        ]