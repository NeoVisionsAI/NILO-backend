"""Node document.

A *node* is a physical device in NILO to which all the monitoring devices
(cameras, microphones, medical monitors...) are connected. It also holds the
network/connectivity configuration and physical placement of that device.

The node access password is stored **encrypted** at rest (it must stay
recoverable so the platform can connect to the device, hence encryption rather
than hashing). The MAC address is unique across nodes.
"""

from datetime import datetime

from beanie import Document
from pymongo import ASCENDING, IndexModel

from app.models.base import TimestampMixin
from app.models.fields import ENCRYPTED_BSON_ENCODERS, EncryptedStr


class Node(Document, TimestampMixin):
    name: str
    mac_address: str

    # --- Network / connectivity ---
    public_ip: str | None = None
    ddns: str | None = None
    bluetooth_enabled: bool = False
    wifi_enabled: bool = False
    wired_enabled: bool = False

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
        # Re-validate on save so the encrypted access_password set via attribute
        # assignment (e.g. on PATCH) is re-wrapped into its marker type and thus
        # actually encrypted at rest (plain assignment would bypass encryption).
        validate_on_save = True
        indexes = [
            IndexModel([("mac_address", ASCENDING)], unique=True),
        ]
