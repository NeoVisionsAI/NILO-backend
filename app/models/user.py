"""User account document.

A single collection holds all user types (root, clinician, patient). Common
fields are shared; role-specific data lives in embedded profiles
(``clinician_profile`` / ``patient_profile``).

Personal data (name, contact, addresses...) is stored **encrypted** at rest
(see ``app/models/fields.py``). The email additionally keeps a deterministic
blind index (``email_bidx``) for login lookups and uniqueness.
"""

from datetime import datetime

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel

from app.models.base import TimestampMixin, utcnow
from app.models.enums import ClinicianType, PatientType, Sex, UserRole
from app.models.fields import (
    ENCRYPTED_BSON_ENCODERS,
    EncryptedDate,
    EncryptedStr,
)


class ClinicianProfile(BaseModel):
    """Extra fields for clinician users."""

    type_clinician: ClinicianType = ClinicianType.OTHER
    institution: str | None = None
    location: str | None = None
    phone_work: EncryptedStr | None = None


class PatientProfile(BaseModel):
    """Extra fields for patient users (monitored subjects).

    The clinician registers these via ``POST /users``. The account may log in
    in the future (e.g. a relative). Monitoring data references the linked
    clinical ``Patient`` record (auto-synced from this profile).
    """

    type_patient: PatientType = PatientType.ADULT
    monitoring_active: bool = False
    # Physical NILO node assigned to this patient for data collection.
    node_id: PydanticObjectId | None = None
    medical_record_number: EncryptedStr | None = None
    sex: Sex = Sex.UNKNOWN
    room: str | None = None
    bed: str | None = None
    notes: EncryptedStr | None = None
    relative_name: EncryptedStr | None = None
    relative_address: EncryptedStr | None = None
    relative_contact: EncryptedStr | None = None


class User(Document, TimestampMixin):
    # --- Common fields (all user types) ---
    name: EncryptedStr
    lastname: EncryptedStr
    type_user: UserRole = UserRole.PATIENT

    # Date of birth (PII, encrypted at rest).
    birthdate: EncryptedDate | None = None
    # User photo stored as a base64 data URI (e.g. "data:image/jpeg;base64,...").
    # Kept in the DB (no physical files) and encrypted at rest for privacy.
    photo: EncryptedStr | None = None

    address: EncryptedStr | None = None
    zip: EncryptedStr | None = None
    country: str | None = None
    phone: EncryptedStr | None = None

    email: EncryptedStr
    # Deterministic HMAC of the (normalized) email for lookups / uniqueness.
    email_bidx: str | None = None

    hashed_password: str
    register_date: datetime = Field(default_factory=utcnow)
    is_active: bool = True

    # Which user registered this account (clinician or root).
    registered_by: PydanticObjectId | None = None

    # --- Role-specific profiles ---
    clinician_profile: ClinicianProfile | None = None
    patient_profile: PatientProfile | None = None

    class Settings:
        name = "users"
        bson_encoders = ENCRYPTED_BSON_ENCODERS
        validate_on_save = True
        indexes = [
            IndexModel([("email_bidx", ASCENDING)], unique=True),
            IndexModel([("type_user", ASCENDING)]),
            IndexModel([("registered_by", ASCENDING)]),
        ]
