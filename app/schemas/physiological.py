"""Physiological reading schemas."""

from datetime import datetime
from typing import Any

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


class PhysiologicalCreate(BaseModel):
    session_id: PydanticObjectId
    patient_id: PydanticObjectId
    node_id: PydanticObjectId | None = Field(
        None,
        description="ObjectId del nodo NILO de origen, si se conoce",
    )
    timestamp: datetime
    device_id: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)


class PhysiologicalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    session_id: PydanticObjectId
    patient_id: PydanticObjectId
    node_id: PydanticObjectId | None = None
    device_id: str | None = None
    timestamp: datetime
    metrics: dict[str, Any]
    units: dict[str, str]
