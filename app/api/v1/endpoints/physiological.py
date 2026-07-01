"""Physiological readings endpoints.

Numeric data is stored as timestamped documents (no object storage needed).
Supports single and bulk insert, plus time-range queries per patient.
"""

from datetime import datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_user, require_staff
from app.models.physiological import PhysiologicalReading
from app.models.user import User
from app.schemas.physiological import PhysiologicalCreate, PhysiologicalOut

router = APIRouter()


@router.post(
    "", response_model=PhysiologicalOut, status_code=status.HTTP_201_CREATED
)
async def create_reading(
    payload: PhysiologicalCreate, _: User = Depends(require_staff)
) -> PhysiologicalReading:
    reading = PhysiologicalReading(**payload.model_dump())
    await reading.insert()
    return reading


@router.post(
    "/bulk",
    response_model=list[PhysiologicalOut],
    status_code=status.HTTP_201_CREATED,
)
async def create_readings_bulk(
    payload: list[PhysiologicalCreate], _: User = Depends(require_staff)
) -> list[PhysiologicalReading]:
    readings = [PhysiologicalReading(**item.model_dump()) for item in payload]
    if readings:
        await PhysiologicalReading.insert_many(readings)
    return readings


@router.get("", response_model=list[PhysiologicalOut])
async def list_readings(
    patient_id: PydanticObjectId,
    start: datetime | None = None,
    end: datetime | None = None,
    skip: int = 0,
    limit: int = Query(default=1000, le=10000),
    _: User = Depends(get_current_user),
) -> list[PhysiologicalReading]:
    conditions = [PhysiologicalReading.patient_id == patient_id]
    if start is not None:
        conditions.append(PhysiologicalReading.timestamp >= start)
    if end is not None:
        conditions.append(PhysiologicalReading.timestamp <= end)
    return (
        await PhysiologicalReading.find(*conditions)
        .sort(+PhysiologicalReading.timestamp)
        .skip(skip)
        .limit(limit)
        .to_list()
    )
