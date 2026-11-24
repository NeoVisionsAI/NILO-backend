"""Beanie document models.

``ALL_DOCUMENT_MODELS`` is used to initialize Beanie on startup.
"""

from app.models.audio import AudioRecording
from app.models.landmarks import BodyLandmarks
from app.models.medical_document import MedicalDocument
from app.models.monitoring_session import MonitoringSession, VideoSegment
from app.models.node import Node
from app.models.pain_event import PainEvent
from app.models.patient import Patient
from app.models.physiological import PhysiologicalReading
from app.models.session_text_note import SessionTextNote
from app.models.user import User

ALL_DOCUMENT_MODELS = [
    User,
    Patient,
    Node,
    MonitoringSession,
    VideoSegment,
    PhysiologicalReading,
    AudioRecording,
    PainEvent,
    BodyLandmarks,
    MedicalDocument,
    SessionTextNote,
]

__all__ = [
    "AudioRecording",
    "BodyLandmarks",
    "MedicalDocument",
    "MonitoringSession",
    "Node",
    "PainEvent",
    "Patient",
    "PhysiologicalReading",
    "User",
    "VideoSegment",
    "SessionTextNote",
    "ALL_DOCUMENT_MODELS",
]
