"""Aggregate router for API v1."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    audio,
    auth,
    landmarks,
    medical_documents,
    pain_events,
    patients,
    physiological,
    recordings,
    users,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(
    patients.router, prefix="/patients", tags=["patients"]
)
api_router.include_router(
    recordings.router, prefix="/recordings", tags=["recordings"]
)
api_router.include_router(
    physiological.router,
    prefix="/physiological",
    tags=["physiological"],
)
api_router.include_router(audio.router, prefix="/audio", tags=["audio"])
api_router.include_router(
    pain_events.router, prefix="/pain-events", tags=["pain-events"]
)
api_router.include_router(
    landmarks.router, prefix="/landmarks", tags=["landmarks"]
)
api_router.include_router(
    medical_documents.router,
    prefix="/medical-documents",
    tags=["medical-documents"],
)
