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
    room: str | None = None
    bed: str | None = None
    notes: str | None = None


class PatientUpdate(BaseModel):
    full_name: str | None = None
    medical_record_number: str | None = None
    birth_date: date | None = None
    sex: Sex | None = None
    patient_type: PatientType | None = None
    room: str | None = None
    bed: str | None = None
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
    room: str | None = None
    bed: str | None = None
    is_active: bool
    notes: str | None = None
    created_at: datetime
