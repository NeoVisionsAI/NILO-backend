"""Monitoring session validation helpers."""

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.models.enums import MonitoringSessionStatus
from app.models.monitoring_session import MonitoringSession
from app.models.node import Node


async def require_node(node_id: PydanticObjectId) -> Node:
    node = await Node.get(node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )
    return node


async def require_session(
    session_id: PydanticObjectId,
    *,
    patient_id: PydanticObjectId | None = None,
    node_id: PydanticObjectId | None = None,
    must_be_active: bool = False,
) -> MonitoringSession:
    session = await MonitoringSession.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitoring session not found",
        )
    if patient_id is not None and session.patient_id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="patient_id does not match the monitoring session",
        )
    if node_id is not None and session.node_id is not None and session.node_id != node_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="node_id does not match the monitoring session",
        )
    if must_be_active and session.status != MonitoringSessionStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Monitoring session is not active",
        )
    return session


async def require_active_ingestion(
    *,
    session_id: PydanticObjectId,
    node_id: PydanticObjectId | None = None,
    patient_id: PydanticObjectId | None = None,
) -> MonitoringSession:
    """Validate session (and node when provided) before ingest."""
    if node_id is not None:
        await require_node(node_id)
    return await require_session(
        session_id,
        patient_id=patient_id,
        node_id=node_id,
        must_be_active=True,
    )


async def count_session_documents(
    document_model: type,
    session_id: PydanticObjectId,
) -> int:
    """Count documents linked to a monitoring session."""
    collection = document_model.get_motor_collection()
    return await collection.count_documents({"session_id": session_id})
