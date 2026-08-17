"""Clinical patient management (monitored subjects).

These are the people being monitored (bed, incubator, etc.). They do **not** log
in. A clinician registers them here; all monitoring data (video, vitals, audio…)
references ``patient_id``.

In the future a relative may log in via a portal ``User`` account linked to one
of these records through ``User.linked_patient_id``.
"""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_current_user, require_staff
from app.core import crypto
from app.core.photo import upload_to_data_uri, validate_photo_data_uri
from app.models.base import utcnow
from app.models.enums import UserRole
from app.models.patient import Patient
from app.models.user import User
from app.schemas.patient import PatientCreate, PatientOut, PatientUpdate

router = APIRouter()


def _can_manage_patient(actor: User, patient: Patient) -> bool:
    if actor.type_user == UserRole.ROOT:
        return True
    if (
        actor.type_user == UserRole.CLINICIAN
        and patient.created_by == actor.id
    ):
        return True
    if (
        actor.type_user == UserRole.PATIENT
        and actor.id == patient.user_id
    ):
        return True
    return False


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
    validate_photo_data_uri(payload.photo)
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
    actor: User = Depends(get_current_user),
) -> list[Patient]:
    if actor.type_user == UserRole.ROOT:
        query = (
            Patient.find(Patient.is_active == True)  # noqa: E712
            if active_only
            else Patient.find_all()
        )
    elif actor.type_user == UserRole.CLINICIAN:
        filters = [Patient.created_by == actor.id]
        if active_only:
            filters.append(Patient.is_active == True)  # noqa: E712
        query = Patient.find(*filters)
    elif actor.type_user == UserRole.PATIENT:
        patient = await Patient.find_one(Patient.user_id == actor.id)
        return [patient] if patient is not None else []
    else:
        return []
    return await query.skip(skip).limit(limit).to_list()


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(
    patient_id: PydanticObjectId, actor: User = Depends(get_current_user)
) -> Patient:
    patient = await Patient.get(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    if not _can_manage_patient(actor, patient):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to view this patient",
        )
    return patient


@router.patch("/{patient_id}", response_model=PatientOut)
async def update_patient(
    patient_id: PydanticObjectId,
    payload: PatientUpdate,
    actor: User = Depends(require_staff),
) -> Patient:
    patient = await Patient.get(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    if not _can_manage_patient(actor, patient):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to update this patient",
        )
    data = payload.model_dump(exclude_unset=True)
    if "photo" in data:
        validate_photo_data_uri(data["photo"])
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


@router.post("/{patient_id}/photo", response_model=PatientOut)
async def upload_patient_photo(
    patient_id: PydanticObjectId,
    file: UploadFile = File(...),
    actor: User = Depends(require_staff),
) -> Patient:
    """Upload/replace a monitored patient's photo (stored as base64 in DB)."""
    patient = await Patient.get(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    if not _can_manage_patient(actor, patient):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to update this patient",
        )
    patient.photo = await upload_to_data_uri(file)
    patient.updated_at = utcnow()
    await patient.save()
    return patient


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: PydanticObjectId, actor: User = Depends(require_staff)
) -> None:
    patient = await Patient.get(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    if not _can_manage_patient(actor, patient):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to delete this patient",
        )
    await patient.delete()
