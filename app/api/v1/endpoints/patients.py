"""Patient management endpoints."""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_staff
from app.core import crypto
from app.models.base import utcnow
from app.models.patient import Patient
from app.models.user import User
from app.schemas.patient import PatientCreate, PatientOut, PatientUpdate

router = APIRouter()


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
async def create_patient(
    payload: PatientCreate, current_user: User = Depends(require_staff)
) -> Patient:
    if payload.medical_record_number:
        existing = await Patient.find_one(
            Patient.mrn_bidx
            == crypto.blind_index(
                payload.medical_record_number, normalize=False
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Medical record number already registered",
            )
    patient = Patient(**payload.model_dump(), created_by=current_user.id)
    if payload.medical_record_number:
        patient.mrn_bidx = crypto.blind_index(
            payload.medical_record_number, normalize=False
        )
    await patient.insert()
    return patient


@router.get("", response_model=list[PatientOut])
async def list_patients(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    _: User = Depends(get_current_user),
) -> list[Patient]:
    query = Patient.find(Patient.is_active == True) if active_only else Patient.find_all()  # noqa: E712
    return await query.skip(skip).limit(limit).to_list()


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(
    patient_id: PydanticObjectId, _: User = Depends(get_current_user)
) -> Patient:
    patient = await Patient.get(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.patch("/{patient_id}", response_model=PatientOut)
async def update_patient(
    patient_id: PydanticObjectId,
    payload: PatientUpdate,
    _: User = Depends(require_staff),
) -> Patient:
    patient = await Patient.get(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(patient, key, value)
    if "medical_record_number" in data:
        patient.mrn_bidx = (
            crypto.blind_index(patient.medical_record_number, normalize=False)
            if patient.medical_record_number
            else None
        )
    patient.updated_at = utcnow()
    await patient.save()
    return patient


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: PydanticObjectId, _: User = Depends(require_staff)
) -> None:
    patient = await Patient.get(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    await patient.delete()
