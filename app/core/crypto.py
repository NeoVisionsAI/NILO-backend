"""Application-level encryption for sensitive fields.

Design
------
- **Confidentiality + integrity** with AES-256-GCM (AEAD). A raw DB dump is
  useless without the master key.
- **Envelope-style key derivation**: from a single base64 master key we derive
  (via HKDF-SHA256) an encryption key and an independent HMAC key. This keeps
  the encryption key and the blind-index key cryptographically separated.
- **Versioned tokens** (``enc:v1:<payload>``) so keys can be rotated later:
  new writes use the active version while old ciphertexts remain decryptable.
- **Blind index**: deterministic HMAC-SHA256 of a normalized value, used to
  search / enforce uniqueness on fields whose value is stored encrypted
  (e.g. user email for login, patient medical record number).

The master key is provided via ``credentials.env`` (``ENCRYPTION_MASTER_KEY``)
and is never stored with the data. The key-loading logic is isolated in
``_load_keys`` so it can be swapped for a KMS/Vault backend in the future.
"""

import base64
import hmac
import os
from hashlib import sha256

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

_TOKEN_PREFIX = "enc"
_ACTIVE_VERSION = "v1"
_NONCE_SIZE = 12  # AES-GCM standard nonce size.


class EncryptionError(RuntimeError):
    pass


def _decode_master_key() -> bytes:
    raw = settings.ENCRYPTION_MASTER_KEY
    try:
        key = base64.b64decode(raw)
    except Exception as exc:  # noqa: BLE001
        raise EncryptionError(
            "ENCRYPTION_MASTER_KEY must be valid base64"
        ) from exc
    if len(key) < 32:
        raise EncryptionError(
            "ENCRYPTION_MASTER_KEY must decode to at least 32 bytes "
            "(use: python -c \"import base64,os; "
            "print(base64.b64encode(os.urandom(32)).decode())\")"
        )
    return key


def _derive(master: bytes, info: bytes, length: int = 32) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=length, salt=None, info=info
    ).derive(master)


def _load_keys(version: str) -> tuple[bytes, bytes]:
    """Return (encryption_key, hmac_key) for a given key version.

    Currently a single master key backs version ``v1``. To rotate, add a new
    version here backed by a new master key and bump ``_ACTIVE_VERSION``.
    """
    if version != "v1":
        raise EncryptionError(f"Unknown key version: {version}")
    master = _decode_master_key()
    enc_key = _derive(master, b"nilo/field-encryption/v1")
    mac_key = _derive(master, b"nilo/blind-index/v1")
    return enc_key, mac_key


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(f"{_TOKEN_PREFIX}:")


def encrypt(plaintext: str) -> str:
    """Encrypt a string, returning a ``enc:v1:<base64>`` token."""
    enc_key, _ = _load_keys(_ACTIVE_VERSION)
    nonce = os.urandom(_NONCE_SIZE)
    ct = AESGCM(enc_key).encrypt(nonce, plaintext.encode("utf-8"), None)
    payload = base64.b64encode(nonce + ct).decode("ascii")
    return f"{_TOKEN_PREFIX}:{_ACTIVE_VERSION}:{payload}"


def decrypt(token: str) -> str:
    """Decrypt a ``enc:<version>:<base64>`` token back to plaintext."""
    try:
        prefix, version, payload = token.split(":", 2)
    except ValueError as exc:
        raise EncryptionError("Malformed ciphertext token") from exc
    if prefix != _TOKEN_PREFIX:
        raise EncryptionError("Not an encryption token")
    enc_key, _ = _load_keys(version)
    raw = base64.b64decode(payload)
    nonce, ct = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
    return AESGCM(enc_key).decrypt(nonce, ct, None).decode("utf-8")


def blind_index(value: str, *, normalize: bool = True) -> str:
    """Deterministic HMAC-SHA256 index for searchable encrypted fields.

    Same input -> same output, enabling equality lookups and unique indexes
    without exposing the plaintext. ``normalize`` lowercases and trims (good
    for emails); disable it for case-sensitive identifiers.
    """
    _, mac_key = _load_keys(_ACTIVE_VERSION)
    material = value.strip().lower() if normalize else value.strip()
    return hmac.new(mac_key, material.encode("utf-8"), sha256).hexdigest()
