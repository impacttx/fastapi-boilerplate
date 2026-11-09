from datetime import UTC, datetime
import hashlib
import hmac
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer
import jwt
from jwt.exceptions import InvalidTokenError
import orjson
from pydantic import BaseModel, Field
from pydantic_core._pydantic_core import ValidationError

from app.core.errors import AccessTokenRequired, InvalidToken, RefreshTokenRequired
from app.database import SessionDep
from app.settings import settings

from .db_service import get_user, token_in_blacklist
from .models import User


class TokenData(BaseModel):
    # JWT Reserved Claims (numeric date claims are Unix timestamps in seconds)
    exp: int = Field(title="Expiration time", description="Expiration time in seconds since epoch")
    nbf: int = Field(title="Not before", description="Not before time in seconds since epoch")
    iss: str = Field(title="Issuer", description="Issuer of the JWT")
    aud: str = Field(title="Audience", description="Audience of the JWT")
    iat: int = Field(title="Issued at", description="Issued at time in seconds since epoch")
    # Custom Claims
    sub: str = Field(title="Subject", description="User data associated with the token")
    jti: str = Field(title="JWT ID", description="Unique identifier for the JWT")
    refresh: bool = False
    role: str = Field(default="customer", title="Role", description="Primary role of the user")


def create_access_token(
    sub: str,
    exp: int = settings.JWT_EXPIRY_TIME,
    refresh: bool = False,
    role: str = "customer",
) -> str:
    now = int(datetime.now(UTC).timestamp())
    data = TokenData(
        exp=now + exp * 60,  # ``exp`` is expressed in minutes
        nbf=now,
        aud=str(settings.JWT_AUDIENCE),
        iss=str(settings.JWT_ISSUER),
        iat=now,
        sub=sub,
        jti=str(uuid4()),
        refresh=refresh,
        role=role,
    )

    return jwt.encode(
        data.model_dump(),
        settings.JWT_PRIVATE_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        key=settings.JWT_PUBLIC_KEY.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
        audience=str(settings.JWT_AUDIENCE),
        issuer=str(settings.JWT_ISSUER),
    )


class TokenBearer(HTTPBearer):
    def __init__(self, auto_error=True):
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request) -> dict[str, Any] | None:
        credentials = await super().__call__(request)
        if not credentials:
            if self.auto_error:
                raise self.make_not_authenticated_error()
            return None

        try:
            token_data = decode_token(credentials.credentials)
        except (InvalidTokenError, ValidationError, orjson.JSONDecodeError) as err:
            if self.auto_error:
                raise self.make_not_authenticated_error() from err
            # Optional auth: a malformed/expired token degrades to anonymous
            return None

        if token_data is None or await token_in_blacklist(token_data["jti"]):
            if self.auto_error:
                raise self.make_not_authenticated_error()
            return None

        try:
            self.verify_token_data(token_data)
        except HTTPException:
            if self.auto_error:
                raise
            return None

        return token_data

    def verify_token_data(self, token_data: dict[str, Any] | None) -> None:
        raise NotImplementedError("Please Override this method in child classes")


class AccessTokenBearer(TokenBearer):
    def verify_token_data(self, token_data: dict[str, Any] | None) -> None:
        if token_data and token_data["refresh"]:
            raise AccessTokenRequired


class RefreshTokenBearer(TokenBearer):
    def verify_token_data(self, token_data: dict[str, Any] | None) -> None:
        if token_data and not token_data["refresh"]:
            raise RefreshTokenRequired


async def get_current_user(
    credentials: Annotated[dict[str, Any], Depends(AccessTokenBearer())],
    db_session: SessionDep,
) -> User:
    user_id = UUID(credentials["sub"])
    if not (user := await get_user(db_session, user_id)):
        raise InvalidToken
    return user


async def get_optional_current_user(
    credentials: Annotated[dict[str, Any], Depends(AccessTokenBearer(auto_error=False))],
    db_session: SessionDep,
) -> User | None:
    """Best-effort identity for public endpoints.

    Any auth problem (no token, expired/invalid token, unknown user)
    degrades to anonymous instead of failing the request, so public
    forms keep working for guests while logged-in visitors get tagged.
    """
    if not credentials:
        return None
    user_id = UUID(credentials["sub"])
    return await get_user(db_session, user_id)


# ---------------------------------------------------------------------------
# Push-token fingerprinting helpers
# ---------------------------------------------------------------------------
# These replace a previous approach that misused RS256 JWTs as an "encryption"
# primitive.  A deterministic HMAC-SHA256 fingerprint is used instead:
#   - No private key needed
#   - Deterministic: same input always produces the same fingerprint
#   - One-way: the raw token is stored as the dict value, not derivable from
#     the fingerprint key alone


def encrypt(token: str) -> str:
    """Return an HMAC-SHA256 fingerprint of *token*.

    Used as a stable, opaque key for the ``notification_tokens`` dict so the
    same push token is never stored twice.
    """
    secret = settings.SECRET_KEY.get_secret_value().encode()
    return hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()


def decrypt(encrypted_token: str) -> str:  # pragma: no cover
    """DEPRECATED - kept for backward-compatibility only.

    The previous implementation returned the plain push token stored as the
    *value* in ``notification_tokens``.  Callers should iterate the dict
    values directly instead of relying on this function.

    Raises ``NotImplementedError`` because HMAC fingerprints are one-way.
    """
    raise NotImplementedError(
        "Push token fingerprints are one-way. Access the plain token via user.notification_tokens.values()."
    )
