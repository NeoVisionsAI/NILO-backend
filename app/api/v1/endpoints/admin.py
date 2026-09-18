"""Root-only administration: patients, clinicians and NILO nodes."""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import require_root
from app.core import crypto
from app.core.photo import validate_photo_data_uri
from app.core.security import hash_password
from app.models.base import utcnow
from app.models.enums import UserRole
from app.models.node import Node
from app.models.user import ClinicianProfile, PatientProfile, User
from app.schemas.admin import AdminClinicianCreate, AdminPatientCreate
from app.schemas.node import NodeCreate, NodeOut, NodeUpdate
from app.schemas.user import UserOut, UserUpdate
from app.services.admin_search import search_nodes, search_users
from app.services.clinical_patient import delete_clinical_patient, sync_clinical_patient
from app.services.node_auth import apply_access_password

router = APIRouter(prefix="/admin", tags=["admin"])


async def _check_email_unique(email: str, exclude_user_id=None) -> None:
    other = await User.find_one(User.email_bidx == crypto.blind_index(email))
    if other is not None and other.id != exclude_user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )


async def _check_mrn_unique(mrn: str | None, exclude_user_id=None) -> None:
    from app.models.patient import Patient

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


async def _apply_user_update(target: User, payload: UserUpdate) -> None:
    data = payload.model_dump(exclude_unset=True)
    if "photo" in data:
        validate_photo_data_uri(data["photo"])
    if "password" in data:
        target.hashed_password = hash_password(data.pop("password"))
    if "email" in data:
        new_email = data.pop("email")
        await _check_email_unique(new_email, exclude_user_id=target.id)
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


# --- Patients ----------------------------------------------------------------


@router.get("/patients", response_model=list[UserOut])
async def admin_list_patients(
    q: str | None = Query(None, description="Free-text search"),
    name: str | None = None,
    lastname: str | None = None,
    email: str | None = None,
    country: str | None = None,
    zip: str | None = Query(None, alias="zip"),
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    _: User = Depends(require_root),
) -> list[User]:
    return await search_users(
        UserRole.PATIENT,
        q=q,
        name=name,
        lastname=lastname,
        email=email,
        country=country,
        zip_code=zip,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/patients", response_model=UserOut, status_code=status.HTTP_201_CREATED
)
async def admin_create_patient(
    payload: AdminPatientCreate,
    actor: User = Depends(require_root),
) -> User:
    await _check_email_unique(payload.email)
    validate_photo_data_uri(payload.photo)
    if payload.patient_profile and payload.patient_profile.medical_record_number:
        await _check_mrn_unique(payload.patient_profile.medical_record_number)

    profile = (
        PatientProfile(**payload.patient_profile.model_dump())
        if payload.patient_profile
        else PatientProfile()
    )
    user = User(
        name=payload.name,
        lastname=payload.lastname,
        type_user=UserRole.PATIENT,
        email=payload.email,
        email_bidx=crypto.blind_index(payload.email),
        hashed_password=hash_password(payload.password),
        birthdate=payload.birthdate,
        photo=payload.photo,
        address=payload.address,
        zip=payload.zip,
        country=payload.country,
        phone=payload.phone,
        is_active=payload.is_active,
        registered_by=actor.id,
        patient_profile=profile,
    )
    await user.insert()
    await sync_clinical_patient(user)
    return user


@router.get("/patients/{user_id}", response_model=UserOut)
async def admin_get_patient(
    user_id: PydanticObjectId, _: User = Depends(require_root)
) -> User:
    user = await User.get(user_id)
    if user is None or user.type_user != UserRole.PATIENT:
        raise HTTPException(status_code=404, detail="Patient not found")
    return user


@router.patch("/patients/{user_id}", response_model=UserOut)
async def admin_update_patient(
    user_id: PydanticObjectId,
    payload: UserUpdate,
    _: User = Depends(require_root),
) -> User:
    user = await User.get(user_id)
    if user is None or user.type_user != UserRole.PATIENT:
        raise HTTPException(status_code=404, detail="Patient not found")
    await _apply_user_update(user, payload)
    await user.save()
    await sync_clinical_patient(user)
    return user


@router.delete("/patients/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_patient(
    user_id: PydanticObjectId, _: User = Depends(require_root)
) -> None:
    user = await User.get(user_id)
    if user is None or user.type_user != UserRole.PATIENT:
        raise HTTPException(status_code=404, detail="Patient not found")
    await delete_clinical_patient(user.id)
    await user.delete()


# --- Clinicians --------------------------------------------------------------


@router.get("/clinicians", response_model=list[UserOut])
async def admin_list_clinicians(
    q: str | None = Query(None, description="Free-text search"),
    name: str | None = None,
    lastname: str | None = None,
    email: str | None = None,
    country: str | None = None,
    zip: str | None = Query(None, alias="zip"),
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    _: User = Depends(require_root),
) -> list[User]:
    return await search_users(
        UserRole.CLINICIAN,
        q=q,
        name=name,
        lastname=lastname,
        email=email,
        country=country,
        zip_code=zip,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/clinicians", response_model=UserOut, status_code=status.HTTP_201_CREATED
)
async def admin_create_clinician(
    payload: AdminClinicianCreate,
    actor: User = Depends(require_root),
) -> User:
    await _check_email_unique(payload.email)
    validate_photo_data_uri(payload.photo)
    profile = (
        ClinicianProfile(**payload.clinician_profile.model_dump())
        if payload.clinician_profile
        else ClinicianProfile()
    )
    user = User(
        name=payload.name,
        lastname=payload.lastname,
        type_user=UserRole.CLINICIAN,
        email=payload.email,
        email_bidx=crypto.blind_index(payload.email),
        hashed_password=hash_password(payload.password),
        birthdate=payload.birthdate,
        photo=payload.photo,
        address=payload.address,
        zip=payload.zip,
        country=payload.country,
        phone=payload.phone,
        is_active=payload.is_active,
        registered_by=actor.id,
        clinician_profile=profile,
    )
    await user.insert()
    return user


@router.get("/clinicians/{user_id}", response_model=UserOut)
async def admin_get_clinician(
    user_id: PydanticObjectId, _: User = Depends(require_root)
) -> User:
    user = await User.get(user_id)
    if user is None or user.type_user != UserRole.CLINICIAN:
        raise HTTPException(status_code=404, detail="Clinician not found")
    return user


@router.patch("/clinicians/{user_id}", response_model=UserOut)
async def admin_update_clinician(
    user_id: PydanticObjectId,
    payload: UserUpdate,
    _: User = Depends(require_root),
) -> User:
    user = await User.get(user_id)
    if user is None or user.type_user != UserRole.CLINICIAN:
        raise HTTPException(status_code=404, detail="Clinician not found")
    await _apply_user_update(user, payload)
    await user.save()
    return user


@router.delete("/clinicians/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_clinician(
    user_id: PydanticObjectId, _: User = Depends(require_root)
) -> None:
    user = await User.get(user_id)
    if user is None or user.type_user != UserRole.CLINICIAN:
        raise HTTPException(status_code=404, detail="Clinician not found")
    await user.delete()


# --- NILO nodes --------------------------------------------------------------


@router.get("/nodes", response_model=list[NodeOut])
async def admin_list_nodes(
    q: str | None = Query(None, description="Free-text search"),
    name: str | None = None,
    mac_address: str | None = None,
    city: str | None = None,
    public_ip: str | None = None,
    ddns: str | None = None,
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    _: User = Depends(require_root),
) -> list[Node]:
    return await search_nodes(
        q=q,
        name=name,
        mac_address=mac_address,
        city=city,
        public_ip=public_ip,
        ddns=ddns,
        skip=skip,
        limit=limit,
    )


@router.post("/nodes", response_model=NodeOut, status_code=status.HTTP_201_CREATED)
async def admin_create_node(
    payload: NodeCreate, _: User = Depends(require_root)
) -> Node:
    existing = await Node.find_one(Node.mac_address == payload.mac_address)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A node with this MAC address already exists",
        )
    data = payload.model_dump()
    password = data.pop("access_password", None)
    node = Node(**data)
    apply_access_password(node, password)
    await node.insert()
    return node


@router.get("/nodes/{node_id}", response_model=NodeOut)
async def admin_get_node(
    node_id: PydanticObjectId, _: User = Depends(require_root)
) -> Node:
    node = await Node.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.patch("/nodes/{node_id}", response_model=NodeOut)
async def admin_update_node(
    node_id: PydanticObjectId,
    payload: NodeUpdate,
    _: User = Depends(require_root),
) -> Node:
    node = await Node.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")

    data = payload.model_dump(exclude_unset=True)
    password = data.pop("access_password", None)
    new_mac = data.get("mac_address")
    if new_mac is not None and new_mac != node.mac_address:
        other = await Node.find_one(Node.mac_address == new_mac)
        if other is not None and other.id != node.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A node with this MAC address already exists",
            )

    for key, value in data.items():
        setattr(node, key, value)
    apply_access_password(node, password)
    node.updated_at = utcnow()
    await node.save()
    return node


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_node(
    node_id: PydanticObjectId, _: User = Depends(require_root)
) -> None:
    node = await Node.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    await node.delete()
