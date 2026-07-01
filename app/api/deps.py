"""Reusable API dependencies: authentication and role-based authorization."""

from beanie import PydanticObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.core.security import decode_access_token
from app.models.enums import UserRole
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login"
)

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    payload = decode_access_token(token)
    if payload is None:
        raise _CREDENTIALS_EXC
    user_id = payload.get("sub")
    if not user_id:
        raise _CREDENTIALS_EXC
    try:
        user = await User.get(PydanticObjectId(user_id))
    except Exception as exc:  # noqa: BLE001 - invalid id format
        raise _CREDENTIALS_EXC from exc
    if user is None or not user.is_active:
        raise _CREDENTIALS_EXC
    return user


def require_roles(*roles: UserRole):
    """Dependency factory enforcing that the user has one of ``roles``.

    ``ROOT`` is always allowed.
    """

    allowed = set(roles) | {UserRole.ROOT}

    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.type_user not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _checker


# Common shortcuts.
require_root = require_roles(UserRole.ROOT)
# Clinicians (and root) are the staff that manage patients and register data.
require_staff = require_roles(UserRole.CLINICIAN)
