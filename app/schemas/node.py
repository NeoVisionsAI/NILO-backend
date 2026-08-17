"""Node schemas: creation, update and output."""

from datetime import datetime

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict


class NodeCreate(BaseModel):
    name: str
    mac_address: str
    public_ip: str | None = None
    ddns: str | None = None
    bluetooth_enabled: bool = False
    wifi_enabled: bool = False
    wired_enabled: bool = False
    address: str | None = None
    zip: str | None = None
    city: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    access_password: str | None = None
    last_update: datetime | None = None
    last_update_ddns: datetime | None = None


class NodeUpdate(BaseModel):
    name: str | None = None
    mac_address: str | None = None
    public_ip: str | None = None
    ddns: str | None = None
    bluetooth_enabled: bool | None = None
    wifi_enabled: bool | None = None
    wired_enabled: bool | None = None
    address: str | None = None
    zip: str | None = None
    city: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    access_password: str | None = None
    last_update: datetime | None = None
    last_update_ddns: datetime | None = None


class NodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    name: str
    mac_address: str
    public_ip: str | None = None
    ddns: str | None = None
    bluetooth_enabled: bool
    wifi_enabled: bool
    wired_enabled: bool
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
