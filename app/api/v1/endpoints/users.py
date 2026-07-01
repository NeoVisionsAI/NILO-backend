"""User management endpoints: register, update, list and get.

Permission rules
----------------
- **root** can register clinicians and patients, and can view/update anyone.
- **clinician** can register only patients; can view/update themselves and the
  patients they registered (``registered_by``).
- **patient** can view/update only themselves.
"""

from pathlib import Path

from beanie import PydanticObjectId
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)

from app.api.deps import get_current_user, require_root
from app.core import crypto
from app.core.config import settings
from app.core.security import hash_password
from app.models.base import utcnow
from app.models.enums import UserRole
from app.models.user import ClinicianProfile, PatientProfile, User
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter()

# Map accepted image content types to file extensions.
_ALLOWED_PHOTO_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _can_register(actor: User, target_type: UserRole) -> bool:
    if actor.type_user == UserRole.ROOT:
        return target_type in (UserRole.CLINICIAN, UserRole.PATIENT)
    if actor.type_user == UserRole.CLINICIAN:
        return target_type == UserRole.PATIENT
    return False


def _can_manage(actor: User, target: User) -> bool:
    """Whether ``actor`` may view/update ``target``."""
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
        address=payload.address,
        zip=payload.zip,
        country=payload.country,
        phone=payload.phone,
        registered_by=actor.id,
        clinician_profile=clinician_profile,
        patient_profile=patient_profile,
    )
    await user.insert()
    return user


@router.get("", response_model=list[UserOut])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    actor: User = Depends(get_current_user),
) -> list[User]:
    if actor.type_user == UserRole.ROOT:
        query = User.find_all()
    elif actor.type_user == UserRole.CLINICIAN:
        # Only the patients this clinician registered.
        query = User.find(
            User.type_user == UserRole.PATIENT,
            User.registered_by == actor.id,
        )
    else:  # patient: only self
        return [actor]
    return await query.skip(skip).limit(limit).to_list()


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
        target.patient_profile = (
            PatientProfile(**pp) if pp is not None else None
        )

    for key, value in data.items():
        setattr(target, key, value)

    target.updated_at = utcnow()
    await target.save()
    return target


@router.post("/{user_id}/photo", response_model=UserOut)
async def upload_photo(
    user_id: PydanticObjectId,
    file: UploadFile = File(...),
    actor: User = Depends(get_current_user),
) -> User:
    """Upload/replace a user's photo.

    The image is stored on the backend filesystem (under ``MEDIA_ROOT``) and the
    user's ``photo_url`` is set to the URL where the backend serves it.
    """
    target = await User.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not _can_manage(actor, target):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to update this user",
        )

    ext = _ALLOWED_PHOTO_TYPES.get(file.content_type or "")
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported image type (allowed: jpeg, png, webp, gif)",
        )

    content = await file.read()
    if len(content) > settings.MAX_PHOTO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Photo exceeds {settings.MAX_PHOTO_BYTES} bytes",
        )

    avatars_dir = Path(settings.MEDIA_ROOT) / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)
    # Remove any previous photo(s) for this user (extension may differ).
    for old in avatars_dir.glob(f"{user_id}.*"):
        old.unlink(missing_ok=True)

    filename = f"{user_id}{ext}"
    (avatars_dir / filename).write_bytes(content)

    target.photo_url = f"{settings.MEDIA_URL_PREFIX}/avatars/{filename}"
    target.updated_at = utcnow()
    await target.save()
    return target


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: PydanticObjectId, _: User = Depends(require_root)
) -> None:
    target = await User.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    await target.delete()
