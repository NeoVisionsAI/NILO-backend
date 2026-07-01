"""Encrypted field types for Beanie documents.

In application memory the value is always plaintext; it is only encrypted when
written to MongoDB and decrypted when read back.

Mechanism
---------
Beanie serializes documents to BSON with its own ``Encoder`` (it does NOT use
pydantic serializers), but the encoder honours per-document ``bson_encoders``.
So we:

- Represent encrypted values with marker subclasses (``EncStr`` / ``EncDate``)
  that still behave like ``str`` / ``date`` in memory (plaintext).
- Register ``bson_encoders`` (see ``ENCRYPTED_BSON_ENCODERS``) so those marker
  types are encrypted on write.
- Use pydantic validators to decrypt on read and to wrap values back into the
  marker subclasses (so the encoder recognizes them).

Each document that uses these types must include ``ENCRYPTED_BSON_ENCODERS`` in
its ``Settings.bson_encoders``.
"""

from datetime import date
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator

from app.core import crypto


class EncStr(str):
    """A ``str`` whose value is stored encrypted in MongoDB."""


class EncDate(date):
    """A ``date`` whose value is stored encrypted in MongoDB."""


def _decrypt_before(value: Any) -> Any:
    if value is None:
        return None
    if crypto.is_encrypted(value):
        return crypto.decrypt(value)
    return value


def _wrap_str(value: str) -> EncStr:
    return EncStr(value)


def _wrap_date(value: date) -> EncDate:
    return EncDate(value.year, value.month, value.day)


def _encode_str(value: EncStr) -> str:
    return crypto.encrypt(str(value))


def _encode_date(value: EncDate) -> str:
    return crypto.encrypt(value.isoformat())


# Register these on every document using encrypted fields.
ENCRYPTED_BSON_ENCODERS: dict[type, Any] = {
    EncStr: _encode_str,
    EncDate: _encode_date,
}

EncryptedStr = Annotated[
    str, BeforeValidator(_decrypt_before), AfterValidator(_wrap_str)
]

EncryptedDate = Annotated[
    date, BeforeValidator(_decrypt_before), AfterValidator(_wrap_date)
]
