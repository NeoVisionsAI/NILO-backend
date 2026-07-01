"""Patient document. Everything else references a patient by id.

Personal data (name, medical record number, birth date, notes) is stored
encrypted. A blind index (``mrn_bidx``) makes the medical record number
searchable/unique without exposing it in the database.
"""

from beanie import Document, PydanticObjectId
from pymongo import ASCENDING, IndexModel

from app.models.base import TimestampMixin
from app.models.enums import PatientType, Sex
from app.models.fields import (
    ENCRYPTED_BSON_ENCODERS,
    EncryptedDate,
    EncryptedStr,
)


class Patient(Document, TimestampMixin):
    full_name: EncryptedStr
    # Human-friendly identifier (e.g. hospital medical record number).
    medical_record_number: EncryptedStr | None = None
    # Deterministic HMAC of the MRN for lookups / uniqueness. Set via
    # crypto.blind_index(mrn, normalize=False) when the patient is created.
    mrn_bidx: str | None = None
    birth_date: EncryptedDate | None = None
    sex: Sex = Sex.UNKNOWN
    patient_type: PatientType = PatientType.ADULT

    # Physical location for the monitoring hardware.
    room: str | None = None
    bed: str | None = None

    is_active: bool = True
    notes: EncryptedStr | None = None

    created_by: PydanticObjectId | None = None

    class Settings:
        name = "patients"
        bson_encoders = ENCRYPTED_BSON_ENCODERS
        # Re-validate on save so values set via attribute assignment (e.g. on
        # PATCH) are re-wrapped into the encrypted marker types and therefore
        # actually encrypted at rest (plain assignment would bypass encryption).
        validate_on_save = True
        indexes = [
            IndexModel(
                [("mrn_bidx", ASCENDING)],
                unique=True,
                partialFilterExpression={"mrn_bidx": {"$type": "string"}},
            ),
        ]
