"""Health check response schemas."""

from pydantic import BaseModel, Field


class ComponentHealth(BaseModel):
    ok: bool
    detail: str | None = None
    latency_ms: float | None = None


class DiskHealth(BaseModel):
    ok: bool
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: float
    level: str = Field(description="ok | warn | critical")


class HealthReport(BaseModel):
    status: str = Field(description="ok | degraded | critical")
    service: str
    environment: str
    ready: bool = Field(description="False if Mongo/MinIO unreachable")
    mongodb: ComponentHealth
    minio: ComponentHealth
    disk: list[DiskHealth]
    disk_status: str = Field(description="ok | warn | critical (worst path)")
