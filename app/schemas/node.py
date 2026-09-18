"""Node schemas: creation, update, output and heartbeat."""

from datetime import datetime
from typing import Any

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


class NodeCreate(BaseModel):
    name: str
    mac_address: str
    private_ip: str | None = None
    public_ip: str | None = None
    ddns: str | None = None
    bluetooth_enabled: bool = False
    wifi_enabled: bool = False
    wired_enabled: bool = False
    ssh_enabled: bool = False
    address: str | None = None
    zip: str | None = None
    city: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    access_password: str | None = None


class NodeUpdate(BaseModel):
    name: str | None = None
    mac_address: str | None = None
    private_ip: str | None = None
    public_ip: str | None = None
    ddns: str | None = None
    bluetooth_enabled: bool | None = None
    wifi_enabled: bool | None = None
    wired_enabled: bool | None = None
    ssh_enabled: bool | None = None
    uptime_seconds: float | None = None
    telemetry: dict[str, Any] | None = None
    address: str | None = None
    zip: str | None = None
    city: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    access_password: str | None = None


class NodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    name: str
    mac_address: str
    private_ip: str | None = None
    public_ip: str | None = None
    ddns: str | None = None
    bluetooth_enabled: bool
    wifi_enabled: bool
    wired_enabled: bool
    ssh_enabled: bool
    uptime_seconds: float | None = None
    telemetry: dict[str, Any] = Field(default_factory=dict)
    last_heartbeat: datetime | None = None
    address: str | None = None
    zip: str | None = None
    city: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    access_password: str | None = None
    last_update: datetime | None = None
    last_update_ddns: datetime | None = None
    created_at: datetime
    updated_at: datetime


class NodeHeartbeat(BaseModel):
    """Sent periodically by nilo-node to refresh reachability / DDNS-style data."""

    mac_address: str
    access_password: str
    private_ip: str | None = None
    public_ip: str | None = None
    ddns: str | None = None
    uptime_seconds: float | None = None
    ssh_enabled: bool | None = None
    bluetooth_enabled: bool | None = None
    wifi_enabled: bool | None = None
    wired_enabled: bool | None = None
    # Extra metrics (versions, CPU, etc.) — merged into node.telemetry.
    telemetry: dict[str, Any] = Field(default_factory=dict)
