"""Schemas for root-only admin endpoints."""

from datetime import date

from pydantic import BaseModel, EmailStr

from app.schemas.user import ClinicianProfileIn, PatientProfileIn


class AdminPatientCreate(BaseModel):
    name: str
    lastname: str
    email: EmailStr
    password: str
    birthdate: date | None = None
    photo: str | None = None
    address: str | None = None
    zip: str | None = None
    country: str | None = None
    phone: str | None = None
    is_active: bool = True
    patient_profile: PatientProfileIn | None = None


class AdminClinicianCreate(BaseModel):
    name: str
    lastname: str
    email: EmailStr
    password: str
    birthdate: date | None = None
    photo: str | None = None
    address: str | None = None
    zip: str | None = None
    country: str | None = None
    phone: str | None = None
    is_active: bool = True
    clinician_profile: ClinicianProfileIn | None = None
