"""Node document.

A *node* is a physical device in NILO to which all the monitoring devices
(cameras, microphones, medical monitors...) are connected. It also holds the
network/connectivity configuration and physical placement of that device.

The node access password is stored **encrypted** at rest (it must stay
recoverable so the platform can connect to the device, hence encryption rather
than hashing). The MAC address is unique across nodes.

Telemetry fields (``private_ip``, ``uptime_seconds``, ``ssh_enabled``,
``telemetry``) are updated by the node itself via ``POST /nodes/heartbeat``.
"""

from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.models.base import TimestampMixin
from app.models.fields import ENCRYPTED_BSON_ENCODERS, EncryptedStr


class Node(Document, TimestampMixin):
    name: str
    mac_address: str

    # --- Network / connectivity ---
    private_ip: str | None = None
    public_ip: str | None = None
    ddns: str | None = None
    bluetooth_enabled: bool = False
    wifi_enabled: bool = False
    wired_enabled: bool = False
    ssh_enabled: bool = False

    # --- Runtime telemetry (reported by nilo-node heartbeat) ---
    uptime_seconds: float | None = None
    # Open bag for future metrics (CPU, disk, versions, etc.).
    telemetry: dict[str, Any] = Field(default_factory=dict)
    last_heartbeat: datetime | None = None

    # --- Physical placement ---
    address: str | None = None
    zip: str | None = None
    city: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    # Access password for the device (encrypted at rest, recoverable).
    access_password: EncryptedStr | None = None

    # Timestamps reported by / about the node.
    last_update: datetime | None = None
    last_update_ddns: datetime | None = None

    class Settings:
        name = "nodes"
        bson_encoders = ENCRYPTED_BSON_ENCODERS
        validate_on_save = True
        indexes = [
            IndexModel([("mac_address", ASCENDING)], unique=True),
            IndexModel([("name", ASCENDING)]),
            IndexModel([("city", ASCENDING)]),
            IndexModel([("public_ip", ASCENDING)]),
        ]
