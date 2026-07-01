"""Physiological reading schemas."""

from datetime import datetime
from typing import Any

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


class PhysiologicalCreate(BaseModel):
    patient_id: PydanticObjectId
    timestamp: datetime
    device_id: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)


class PhysiologicalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    patient_id: PydanticObjectId
    device_id: str | None = None
    timestamp: datetime
    metrics: dict[str, Any]
    units: dict[str, str]
