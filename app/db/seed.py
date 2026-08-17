"""Optional demo data created at startup."""

import logging

from beanie import PydanticObjectId

from app.core import crypto
from app.core.config import settings
from app.core.security import hash_password
from app.models.enums import ClinicianType, PatientType, UserRole
from app.models.user import ClinicianProfile, PatientProfile, User
from app.services.clinical_patient import sync_clinical_patient

logger = logging.getLogger("nilo")


async def _ensure_user(
    *,
    email: str | None,
    password: str | None,
    name: str,
    lastname: str,
    type_user: UserRole,
    registered_by: PydanticObjectId | None = None,
    clinician_profile: ClinicianProfile | None = None,
    patient_profile: PatientProfile | None = None,
) -> User | None:
    if not email or not password:
        return None

    existing = await User.find_one(User.email_bidx == crypto.blind_index(email))
    if existing is not None:
        return existing

    user = User(
        name=name,
        lastname=lastname,
        type_user=type_user,
        email=email,
        email_bidx=crypto.blind_index(email),
        hashed_password=hash_password(password),
        registered_by=registered_by,
        clinician_profile=clinician_profile,
        patient_profile=patient_profile,
    )
    await user.insert()
    logger.info("Seeded %s user '%s'", type_user.value, email)
    return user


async def seed_demo_users() -> None:
    if not settings.SEED_USERS:
        return

    root = await User.find_one(
        User.email_bidx == crypto.blind_index(settings.ROOT_EMAIL)
    )
    root_id = root.id if root is not None else None

    clinician = await _ensure_user(
        email=settings.SEED_CLINICIAN_EMAIL,
        password=settings.SEED_CLINICIAN_PASSWORD,
        name="Clara",
        lastname="Clinician",
        type_user=UserRole.CLINICIAN,
        registered_by=root_id,
        clinician_profile=ClinicianProfile(
            type_clinician=ClinicianType.DOCTOR,
            institution="Hospital NILO",
            location="Madrid",
        ),
    )

    patient = await _ensure_user(
        email=settings.SEED_PATIENT_EMAIL,
        password=settings.SEED_PATIENT_PASSWORD,
        name="Pablo",
        lastname="Patient",
        type_user=UserRole.PATIENT,
        registered_by=clinician.id if clinician is not None else root_id,
        patient_profile=PatientProfile(
            type_patient=PatientType.ADULT,
            monitoring_active=True,
            medical_record_number="MRN-DEMO-001",
            relative_contact="+34600000000",
        ),
    )
    if patient is not None:
        await sync_clinical_patient(patient)
