"""User management: accounts that can log in.

The clinician registers **patients** here (``POST /users`` with
``type_user: patient``). That user is passive for now but may log in in the
future (e.g. a relative). A clinical ``Patient`` record is auto-created in the
background for monitoring data (video, vitals…).

Permission rules
----------------
- **root** can register clinicians and patients; can view/update anyone.
- **clinician** can register patients; can view/update themselves and patients
  they registered (``registered_by``).
- **patient** can view/update only themselves.
"""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_current_user, require_root
from app.core import crypto
from app.core.photo import upload_to_data_uri, validate_photo_data_uri
from app.core.security import hash_password
from app.models.base import utcnow
from app.models.enums import UserRole
from app.models.node import Node
from app.models.patient import Patient
from app.models.user import ClinicianProfile, PatientProfile, User
from app.schemas.user import (
    AssignNodeRequest,
    MonitoringActivePatientOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services.clinical_patient import (
    delete_clinical_patient,
    sync_clinical_patient,
)

router = APIRouter()


def _can_register(actor: User, target_type: UserRole) -> bool:
    if actor.type_user == UserRole.ROOT:
        return target_type in (UserRole.CLINICIAN, UserRole.PATIENT)
    if actor.type_user == UserRole.CLINICIAN:
        return target_type == UserRole.PATIENT
    return False


def _can_manage(actor: User, target: User) -> bool:
    if actor.type_user == UserRole.ROOT:
        return True
    if actor.id == target.id:
        return True
    if (
        actor.type_user == UserRole.CLINICIAN
        and target.type_user == UserRole.PATIENT
        and target.registered_by == actor.id
    ):
        return True
    return False


async def _check_mrn_unique(mrn: str | None, exclude_user_id=None) -> None:
    if not mrn:
        return
    bidx = crypto.blind_index(mrn, normalize=False)
    existing = await Patient.find_one(Patient.mrn_bidx == bidx)
    if existing is not None:
        if exclude_user_id and existing.user_id == exclude_user_id:
            return
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medical record number already registered",
        )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserCreate, actor: User = Depends(get_current_user)
) -> User:
    if not _can_register(actor, payload.type_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to register this type of user",
        )

    existing = await User.find_one(
        User.email_bidx == crypto.blind_index(payload.email)
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    validate_photo_data_uri(payload.photo)

    if payload.patient_profile and payload.patient_profile.medical_record_number:
        await _check_mrn_unique(payload.patient_profile.medical_record_number)

    clinician_profile = (
        ClinicianProfile(**payload.clinician_profile.model_dump())
        if payload.clinician_profile is not None
        else None
    )
    patient_profile = (
        PatientProfile(**payload.patient_profile.model_dump())
        if payload.patient_profile is not None
        else None
    )

    user = User(
        name=payload.name,
        lastname=payload.lastname,
        type_user=payload.type_user,
        email=payload.email,
        email_bidx=crypto.blind_index(payload.email),
        hashed_password=hash_password(payload.password),
        birthdate=payload.birthdate,
        photo=payload.photo,
        address=payload.address,
        zip=payload.zip,
        country=payload.country,
        phone=payload.phone,
        registered_by=actor.id,
        clinician_profile=clinician_profile,
        patient_profile=patient_profile,
    )
    await user.insert()

    if user.type_user == UserRole.PATIENT:
        await sync_clinical_patient(user)

    return user


@router.get("", response_model=list[UserOut])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    type_user: UserRole | None = None,
    actor: User = Depends(get_current_user),
) -> list[User]:
    if actor.type_user == UserRole.ROOT:
        query = User.find_all()
        if type_user is not None:
            query = User.find(User.type_user == type_user)
    elif actor.type_user == UserRole.CLINICIAN:
        query = User.find(
            User.type_user == UserRole.PATIENT,
            User.registered_by == actor.id,
        )
    else:
        return [actor]
    return await query.skip(skip).limit(limit).to_list()


@router.get("/monitoring-active", response_model=list[MonitoringActivePatientOut])
async def list_monitoring_active_patients(
    actor: User = Depends(get_current_user),
) -> list[User]:
    """Patients owned by the clinician (or all, for root) with monitoring on."""
    if actor.type_user == UserRole.ROOT:
        query = User.find(
            User.type_user == UserRole.PATIENT,
            User.patient_profile.monitoring_active == True,  # noqa: E712
        )
    elif actor.type_user == UserRole.CLINICIAN:
        query = User.find(
            User.type_user == UserRole.PATIENT,
            User.registered_by == actor.id,
            User.patient_profile.monitoring_active == True,  # noqa: E712
        )
    else:
        return []
    return await query.to_list()


@router.get("/me", response_model=UserOut)
async def read_me(actor: User = Depends(get_current_user)) -> User:
    return actor


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: PydanticObjectId, actor: User = Depends(get_current_user)
) -> User:
    target = await User.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not _can_manage(actor, target):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to view this user",
        )
    return target


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: PydanticObjectId,
    payload: UserUpdate,
    actor: User = Depends(get_current_user),
) -> User:
    target = await User.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not _can_manage(actor, target):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to update this user",
        )

    data = payload.model_dump(exclude_unset=True)

    if "photo" in data:
        validate_photo_data_uri(data["photo"])
    if "password" in data:
        target.hashed_password = hash_password(data.pop("password"))
    if "email" in data:
        new_email = data.pop("email")
        other = await User.find_one(
            User.email_bidx == crypto.blind_index(new_email)
        )
        if other is not None and other.id != target.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        target.email = new_email
        target.email_bidx = crypto.blind_index(new_email)
    if "clinician_profile" in data:
        cp = data.pop("clinician_profile")
        target.clinician_profile = (
            ClinicianProfile(**cp) if cp is not None else None
        )
    if "patient_profile" in data:
        pp = data.pop("patient_profile")
        if pp and pp.get("medical_record_number"):
            await _check_mrn_unique(
                pp["medical_record_number"], exclude_user_id=target.id
            )
        target.patient_profile = (
            PatientProfile(**pp) if pp is not None else None
        )

    for key, value in data.items():
        setattr(target, key, value)

    target.updated_at = utcnow()
    await target.save()

    if target.type_user == UserRole.PATIENT:
        await sync_clinical_patient(target)

    return target


@router.patch("/{user_id}/node", response_model=UserOut)
async def assign_node_to_patient(
    user_id: PydanticObjectId,
    payload: AssignNodeRequest,
    actor: User = Depends(get_current_user),
) -> User:
    """Assign (or unassign) a NILO node to a patient user.

    Pass ``node_id: null`` to remove the current assignment.
    """
    target = await User.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not _can_manage(actor, target):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to update this user",
        )
    if target.type_user != UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only patient users can be assigned a node",
        )

    if payload.node_id is not None:
        node = await Node.get(payload.node_id)
        if node is None:
            raise HTTPException(status_code=404, detail="Node not found")

    base = (
        target.patient_profile.model_dump()
        if target.patient_profile is not None
        else {}
    )
    base["node_id"] = payload.node_id
    target.patient_profile = PatientProfile(**base)
    target.updated_at = utcnow()
    await target.save()
    await sync_clinical_patient(target)
    return target


@router.post("/{user_id}/photo", response_model=UserOut)
async def upload_photo(
    user_id: PydanticObjectId,
    file: UploadFile = File(...),
    actor: User = Depends(get_current_user),
) -> User:
    target = await User.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not _can_manage(actor, target):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to update this user",
        )
    target.photo = await upload_to_data_uri(file)
    target.updated_at = utcnow()
    await target.save()
    if target.type_user == UserRole.PATIENT:
        await sync_clinical_patient(target)
    return target


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: PydanticObjectId, actor: User = Depends(get_current_user)
) -> None:
    target = await User.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if actor.type_user != UserRole.ROOT and not (
        actor.type_user == UserRole.CLINICIAN
        and target.type_user == UserRole.PATIENT
        and target.registered_by == actor.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to delete this user",
        )
    if target.type_user == UserRole.PATIENT:
        await delete_clinical_patient(target.id)
    await target.delete()
