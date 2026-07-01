"""Password hashing and JWT helpers."""

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# JWT ``type`` claim values, used to tell access and refresh tokens apart so a
# refresh token can never be used to access protected endpoints and viceversa.
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def _prepare(password: str) -> bytes:
    """Pre-hash the password so bcrypt's 72-byte limit never truncates it.

    We SHA-256 the password and base64-encode the digest (44 bytes) before
    handing it to bcrypt. This supports arbitrarily long passwords safely.
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            _prepare(plain_password), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def _create_token(
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    to_encode: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + expires_delta,
        "type": token_type,
    }
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_access_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a short-lived signed JWT access token.

    ``subject`` is stored in the ``sub`` claim (typically the user id).
    """
    delta = expires_delta or timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return _create_token(subject, TOKEN_TYPE_ACCESS, delta, extra_claims)


def create_refresh_token(
    subject: str, expires_delta: timedelta | None = None
) -> str:
    """Create a long-lived refresh token used to mint new access tokens."""
    delta = expires_delta or timedelta(
        minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES
    )
    return _create_token(subject, TOKEN_TYPE_REFRESH, delta)


def decode_token(
    token: str, expected_type: str | None = None
) -> dict[str, Any] | None:
    """Decode and validate a JWT.

    Returns the payload, or ``None`` if the signature/expiry is invalid or the
    ``type`` claim does not match ``expected_type`` (when provided).
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        return None
    if expected_type is not None and payload.get("type") != expected_type:
        return None
    return payload


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Backwards-compatible helper: decode a token and require it be an access token."""
    return decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
