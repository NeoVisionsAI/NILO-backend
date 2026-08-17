"""Keep the clinical ``Patient`` record in sync with a patient ``User``.

The clinician registers patients via ``POST /users`` (``type_user == patient``).
That user account is the source of truth for the dashboard and future login.
A linked clinical ``Patient`` document is created/updated automatically so
monitoring data (video, vitals, audio…) can reference ``patient_id``.
"""

from beanie import PydanticObjectId

from app.core import crypto
from app.models.enums import UserRole
from app.models.patient import Patient
from app.models.user import PatientProfile, User


def _full_name(user: User) -> str:
    return f"{user.name} {user.lastname}".strip()


async def sync_clinical_patient(user: User) -> Patient | None:
    """Create or update the clinical record for a patient user."""
    if user.type_user != UserRole.PATIENT or user.patient_profile is None:
        return None

    profile: PatientProfile = user.patient_profile
    existing = await Patient.find_one(Patient.user_id == user.id)

    mrn_bidx = None
    if profile.medical_record_number:
        mrn_bidx = crypto.blind_index(
            profile.medical_record_number, normalize=False
        )
        # Legacy/orphan clinical rows may exist without user_id (e.g. after seed
        # changes). Re-link by MRN instead of inserting a duplicate.
        if existing is None:
            existing = await Patient.find_one(Patient.mrn_bidx == mrn_bidx)

    fields = dict(
        user_id=user.id,
        full_name=_full_name(user),
        medical_record_number=profile.medical_record_number,
        mrn_bidx=mrn_bidx,
        birth_date=user.birthdate,
        sex=profile.sex,
        patient_type=profile.type_patient,
        photo=user.photo,
        room=profile.room,
        bed=profile.bed,
        monitoring_active=profile.monitoring_active,
        node_id=profile.node_id,
        relative_name=profile.relative_name,
        relative_contact=profile.relative_contact,
        relative_address=profile.relative_address,
        notes=profile.notes,
        is_active=user.is_active,
        created_by=user.registered_by,
    )

    if existing is None:
        patient = Patient(**fields)
        await patient.insert()
        return patient

    for key, value in fields.items():
        setattr(existing, key, value)
    await existing.save()
    return existing


async def delete_clinical_patient(user_id: PydanticObjectId) -> None:
    patient = await Patient.find_one(Patient.user_id == user_id)
    if patient is not None:
        await patient.delete()
