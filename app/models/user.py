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
from app.models.enums import ClinicianType, PatientType, UserRole
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
    """Extra fields for patient users."""

    type_patient: PatientType = PatientType.ADULT
    # Whether data is currently being collected for this patient. Distinct from
    # the account-level ``is_active`` flag (which controls login/access).
    monitoring_active: bool = False
    relative_address: EncryptedStr | None = None
    relative_contact: EncryptedStr | None = None


class User(Document, TimestampMixin):
    # --- Common fields (all user types) ---
    name: EncryptedStr
    lastname: EncryptedStr
    type_user: UserRole = UserRole.PATIENT

    # Date of birth (PII, encrypted at rest).
    birthdate: EncryptedDate | None = None
    # URL/path to the user's photo, served by this backend (see MEDIA_URL_PREFIX).
    # The binary lives on the backend filesystem, not in MinIO.
    photo_url: str | None = None

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

    # Which user (clinician/root) registered this account. Used for the
    # "a clinician only sees the patients they registered" rule.
    registered_by: PydanticObjectId | None = None

    # --- Role-specific profiles ---
    clinician_profile: ClinicianProfile | None = None
    patient_profile: PatientProfile | None = None

    class Settings:
        name = "users"
        bson_encoders = ENCRYPTED_BSON_ENCODERS
        # Re-validate on save so values set via attribute assignment (e.g. on
        # PATCH) are re-wrapped into the encrypted marker types and therefore
        # actually encrypted at rest (plain assignment would bypass encryption).
        validate_on_save = True
        indexes = [
            IndexModel([("email_bidx", ASCENDING)], unique=True),
            IndexModel([("type_user", ASCENDING)]),
            IndexModel([("registered_by", ASCENDING)]),
        ]
