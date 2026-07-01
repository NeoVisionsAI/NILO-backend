"""Physiological readings from medical monitors.

The set of measured attributes is intentionally variable (heart rate, SpO2,
and an open-ended set of others), so measurements are stored as a flexible
map ``metrics`` of name -> value plus an optional units map.
"""

from datetime import datetime
from typing import Any

from beanie import Document, Indexed, PydanticObjectId
from pydantic import Field

from app.models.base import TimestampMixin


class PhysiologicalReading(Document, TimestampMixin):
    patient_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]
    device_id: str | None = None
    # Instant the reading was captured (UTC).
    timestamp: Indexed(datetime)  # type: ignore[valid-type]

    # Open-ended metrics, e.g. {"heart_rate": 72, "spo2": 98}.
    metrics: dict[str, Any] = Field(default_factory=dict)
    # Optional units per metric, e.g. {"heart_rate": "bpm", "spo2": "%"}.
    units: dict[str, str] = Field(default_factory=dict)

    class Settings:
        name = "physiological_readings"
