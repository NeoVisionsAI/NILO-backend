"""Shared domain enumerations."""

from enum import Enum


class UserRole(str, Enum):
    ROOT = "root"
    CLINICIAN = "clinician"
    PATIENT = "patient"


class ClinicianType(str, Enum):
    DOCTOR = "doctor"
    NURSE = "nurse"
    TECHNICIAN = "technician"
    RESEARCHER = "researcher"
    OTHER = "other"


class PatientType(str, Enum):
    ADULT = "adult"
    CHILD = "child"
    NEONATE = "neonate"
    OTHER = "other"


class Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"


class RecordingStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"


class SegmentFormat(str, Enum):
    FMP4 = "fmp4"
    MP4 = "mp4"
    HLS_TS = "hls_ts"
    HLS_FMP4 = "hls_fmp4"


class SegmentKind(str, Enum):
    # Short segment intended for live viewing (HLS).
    LIVE = "live"
    # Consolidated long chunk intended for archival/storage.
    ARCHIVE = "archive"


class ProcessingStatus(str, Enum):
    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class AudioKind(str, Enum):
    AMBIENT = "ambient"
    VOICE_NOTE = "voice_note"


class TranscriptionStatus(str, Enum):
    NONE = "none"
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class LandmarkSource(str, Enum):
    MEDIAPIPE = "mediapipe"
    YOLO = "yolo"
    OTHER = "other"


class DocumentType(str, Enum):
    REPORT = "report"
    LAB_RESULT = "lab_result"
    IMAGING = "imaging"
    OTHER = "other"
