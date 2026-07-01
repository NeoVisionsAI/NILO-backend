"""User schemas: registration, update and output."""

from datetime import date, datetime

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, EmailStr, model_validator

from app.models.enums import ClinicianType, PatientType, UserRole


# --- Embedded profiles ---
class ClinicianProfileIn(BaseModel):
    type_clinician: ClinicianType = ClinicianType.OTHER
    institution: str | None = None
    location: str | None = None
    phone_work: str | None = None


class PatientProfileIn(BaseModel):
    type_patient: PatientType = PatientType.ADULT
    monitoring_active: bool = False
    relative_address: str | None = None
    relative_contact: str | None = None


# --- Registration ---
class UserCreate(BaseModel):
    name: str
    lastname: str
    type_user: UserRole
    email: EmailStr
    password: str

    birthdate: date | None = None
    address: str | None = None
    zip: str | None = None
    country: str | None = None
    phone: str | None = None

    clinician_profile: ClinicianProfileIn | None = None
    patient_profile: PatientProfileIn | None = None

    @model_validator(mode="after")
    def _check_profile_matches_type(self) -> "UserCreate":
        if self.type_user == UserRole.CLINICIAN:
            if self.clinician_profile is None:
                self.clinician_profile = ClinicianProfileIn()
            self.patient_profile = None
        elif self.type_user == UserRole.PATIENT:
            if self.patient_profile is None:
                self.patient_profile = PatientProfileIn()
            self.clinician_profile = None
        else:  # root
            self.clinician_profile = None
            self.patient_profile = None
        return self


# --- Update (partial) ---
class UserUpdate(BaseModel):
    name: str | None = None
    lastname: str | None = None
    email: EmailStr | None = None
    password: str | None = None
    birthdate: date | None = None
    address: str | None = None
    zip: str | None = None
    country: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    clinician_profile: ClinicianProfileIn | None = None
    patient_profile: PatientProfileIn | None = None


# --- Output ---
class ClinicianProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type_clinician: ClinicianType
    institution: str | None = None
    location: str | None = None
    phone_work: str | None = None


class PatientProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type_patient: PatientType
    monitoring_active: bool
    relative_address: str | None = None
    relative_contact: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    name: str
    lastname: str
    type_user: UserRole
    # Plain str on output (already validated as EmailStr on input); avoids
    # response-validation failures for reserved domains like ``.local``.
    email: str
    birthdate: date | None = None
    photo_url: str | None = None
    address: str | None = None
    zip: str | None = None
    country: str | None = None
    phone: str | None = None
    register_date: datetime
    is_active: bool
    registered_by: PydanticObjectId | None = None
    clinician_profile: ClinicianProfileOut | None = None
    patient_profile: PatientProfileOut | None = None
