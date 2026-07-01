"""Authentication endpoints."""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import get_current_user
from app.core import crypto
from app.core.security import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import RefreshRequest, Token
from app.schemas.user import UserOut

router = APIRouter()


def _issue_tokens(user: User) -> Token:
    """Mint a fresh access + refresh token pair for ``user``."""
    access = create_access_token(
        subject=str(user.id), extra_claims={"role": user.type_user.value}
    )
    refresh = create_refresh_token(subject=str(user.id))
    return Token(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    """OAuth2 password login. Username field must contain the email."""
    user = await User.find_one(
        User.email_bidx == crypto.blind_index(form_data.username)
    )
    if user is None or not verify_password(
        form_data.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user"
        )
    return _issue_tokens(user)


@router.post("/refresh", response_model=Token)
async def refresh_tokens(body: RefreshRequest) -> Token:
    """Exchange a valid refresh token for a new access + refresh token pair.

    Rotating the refresh token on every call lets the client stay logged in
    indefinitely as long as it refreshes within the refresh window.
    """
    payload = decode_token(body.refresh_token, expected_type=TOKEN_TYPE_REFRESH)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    user = None
    if user_id:
        try:
            user = await User.get(PydanticObjectId(user_id))
        except Exception:  # noqa: BLE001 - malformed id in token
            user = None
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _issue_tokens(user)


@router.get("/me", response_model=UserOut)
async def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
