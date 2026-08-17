"""Patient schemas."""

from datetime import date, datetime

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict

from app.models.enums import PatientType, Sex


class PatientCreate(BaseModel):
    full_name: str
    medical_record_number: str | None = None
    birth_date: date | None = None
    sex: Sex = Sex.UNKNOWN
    patient_type: PatientType = PatientType.ADULT
    # Photo as a base64 data URI, e.g. "data:image/jpeg;base64,/9j/4AAQ...".
    photo: str | None = None
    room: str | None = None
    bed: str | None = None
    monitoring_active: bool = False
    relative_name: str | None = None
    relative_contact: str | None = None
    relative_address: str | None = None
    notes: str | None = None


class PatientUpdate(BaseModel):
    full_name: str | None = None
    medical_record_number: str | None = None
    birth_date: date | None = None
    sex: Sex | None = None
    patient_type: PatientType | None = None
    photo: str | None = None
    room: str | None = None
    bed: str | None = None
    monitoring_active: bool | None = None
    relative_name: str | None = None
    relative_contact: str | None = None
    relative_address: str | None = None
    is_active: bool | None = None
    notes: str | None = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    full_name: str
    medical_record_number: str | None = None
    birth_date: date | None = None
    sex: Sex
    patient_type: PatientType
    # Base64 data URI (as stored). Directly usable in an <img src="...">.
    photo: str | None = None
    room: str | None = None
    bed: str | None = None
    monitoring_active: bool
    relative_name: str | None = None
    relative_contact: str | None = None
    relative_address: str | None = None
    is_active: bool
    notes: str | None = None
    created_by: PydanticObjectId | None = None
    created_at: datetime
    updated_at: datetime
