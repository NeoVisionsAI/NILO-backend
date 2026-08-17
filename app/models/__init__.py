"""Beanie document models.

``ALL_DOCUMENT_MODELS`` is used to initialize Beanie on startup.
"""

from app.models.audio import AudioRecording
from app.models.landmarks import BodyLandmarks
from app.models.medical_document import MedicalDocument
from app.models.node import Node
from app.models.pain_event import PainEvent
from app.models.patient import Patient
from app.models.physiological import PhysiologicalReading
from app.models.recording import Recording, VideoSegment
from app.models.user import User

ALL_DOCUMENT_MODELS = [
    User,
    Patient,
    Node,
    Recording,
    VideoSegment,
    PhysiologicalReading,
    AudioRecording,
    PainEvent,
    BodyLandmarks,
    MedicalDocument,
]

__all__ = [
    "AudioRecording",
    "BodyLandmarks",
    "MedicalDocument",
    "Node",
    "PainEvent",
    "Patient",
    "PhysiologicalReading",
    "Recording",
    "VideoSegment",
    "User",
    "ALL_DOCUMENT_MODELS",
]
