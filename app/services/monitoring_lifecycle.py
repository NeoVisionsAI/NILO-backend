"""Start/stop patient monitoring with a single active MonitoringSession."""

import logging
from io import BytesIO

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.core.config import settings
from app.models.base import utcnow
from app.models.enums import MonitoringSessionStatus, UserRole
from app.models.monitoring_session import MonitoringSession
from app.models.patient import Patient
from app.models.user import PatientProfile, User
from app.services.clinical_patient import sync_clinical_patient
from app.services.monitoring_session import require_node
from app.storage import minio_client

logger = logging.getLogger("nilo.monitoring_lifecycle")


async def _clinical_patient_for_user(user: User) -> Patient:
    if user.type_user != UserRole.PATIENT or user.patient_profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a patient",
        )
    patient = await sync_clinical_patient(user)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Clinical patient record missing",
        )
    return patient


async def _close_active_sessions(patient_id: PydanticObjectId) -> None:
    active = await MonitoringSession.find(
        MonitoringSession.patient_id == patient_id,
        MonitoringSession.status == MonitoringSessionStatus.ACTIVE,
    ).to_list()
    now = utcnow()
    for session in active:
        session.status = MonitoringSessionStatus.COMPLETED
        session.ended_at = now
        session.updated_at = now
        await session.save()


def _write_session_marker(patient_id: PydanticObjectId, session_id: PydanticObjectId) -> None:
    key = f"patients/{patient_id}/sessions/{session_id}/.session"
    try:
        client = minio_client.get_minio()
        client.put_object(
            settings.MINIO_BUCKET,
            key,
            BytesIO(b""),
            0,
            content_type="application/octet-stream",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Session marker not written (%s): %s", key, exc)


async def start_patient_monitoring(user: User) -> tuple[User, MonitoringSession]:
    """Open monitoring: new active session, flags, active_session_id."""
    patient = await _clinical_patient_for_user(user)
    profile = user.patient_profile
    assert profile is not None

    if profile.active_session_id is not None:
        existing = await MonitoringSession.get(profile.active_session_id)
        if (
            existing is not None
            and existing.status == MonitoringSessionStatus.ACTIVE
        ):
            profile.monitoring_active = True
            user.updated_at = utcnow()
            await user.save()
            await sync_clinical_patient(user)
            return user, existing

    await _close_active_sessions(patient.id)

    node_id = profile.node_id
    if node_id is not None:
        await require_node(node_id)

    session = MonitoringSession(
        patient_id=patient.id,
        node_id=node_id,
        archive_chunk_seconds=settings.DEFAULT_VIDEO_CHUNK_SECONDS,
        hls_segment_seconds=settings.DEFAULT_HLS_SEGMENT_SECONDS,
    )
    await session.insert()
    session.external_session_id = str(session.id)
    await session.save()

    profile.monitoring_active = True
    profile.active_session_id = session.id
    user.patient_profile = profile
    user.updated_at = utcnow()
    await user.save()
    await sync_clinical_patient(user)
    _write_session_marker(patient.id, session.id)
    return user, session


async def stop_patient_monitoring(user: User) -> User:
    """Close active session and clear active_session_id."""
    if user.type_user != UserRole.PATIENT or user.patient_profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a patient",
        )
    profile = user.patient_profile
    now = utcnow()

    if profile.active_session_id is not None:
        session = await MonitoringSession.get(profile.active_session_id)
        if session is not None and session.status == MonitoringSessionStatus.ACTIVE:
            session.status = MonitoringSessionStatus.COMPLETED
            session.ended_at = now
            session.updated_at = now
            await session.save()

    profile.monitoring_active = False
    profile.active_session_id = None
    user.patient_profile = profile
    user.updated_at = now
    await user.save()
    await sync_clinical_patient(user)
    return user