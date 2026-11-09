"""
Unit tests for the ``/auth`` endpoints.

All external side-effects (OTP storage, blacklist, SMS delivery) are mocked
so these tests do not depend on Redis, an SMS gateway, or the production DB
connection used inside the OTP/blacklist helpers.

Auth flow under test:
  POST /auth/get_otp        - sends OTP to an EXISTING, ACTIVE account
  POST /auth/register       - creates an INACTIVE account and sends OTP (no OTP in request)
  POST /auth/verify_account - verifies OTP, ACTIVATES account, returns JWT tokens
  POST /auth/login          - sends OTP + verifies it for an ACTIVE account
  POST /auth/refresh_token  - rotates tokens
  POST /auth/logout         - revokes token
"""

from unittest.mock import AsyncMock, MagicMock, patch

from httpx2 import AsyncClient
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.hashing import hash_content
from app.auth.models import User
from app.auth.security import create_access_token, decode_token
from app.core.models import Revision
from app.rbac import db_service as rbac_db_service
from app.rbac.schemas import UserRole
from app.settings import settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_MOBILE = "+919876543210"
TEST_OTP = "123456"
TNC_REVISION = Revision.V1_0.value


def _hashed_test_otp() -> str:
    return hash_content(TEST_OTP)


# ---------------------------------------------------------------------------
# POST /auth/get_otp
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_otp_returns_200_with_otp_in_dev(async_client: AsyncClient, session: AsyncSession):
    """In development mode the response body should contain the plaintext OTP.
    The endpoint now requires an *existing, active* account — mock the lookup.
    """
    active_user = User(mobile_number=VALID_MOBILE, is_active=True)

    with (
        patch("app.auth.routes.db_service.find_user_by_mobile_number", new=AsyncMock(return_value=active_user)),
        patch("app.auth.routes.generate_otp", new=MagicMock(return_value=TEST_OTP)),
        patch("app.auth.routes.db_service.add_otp_for_verification", new=AsyncMock()),
        patch("app.auth.routes.send_otp", new=AsyncMock()),
    ):
        response = await async_client.post("/auth/get_otp", json={"mobile_number": VALID_MOBILE})

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "OTP sent successfully"
    assert "expiry_minutes" in data
    # ENVIRONMENT is "development" in .env.test → OTP is echoed back
    assert data["otp"] == TEST_OTP


@pytest.mark.asyncio
async def test_get_otp_no_account_returns_404(async_client: AsyncClient):
    """Requesting OTP for a number with no active account should return 404."""
    with patch("app.auth.routes.db_service.find_user_by_mobile_number", new=AsyncMock(return_value=None)):
        response = await async_client.post("/auth/get_otp", json={"mobile_number": VALID_MOBILE})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_otp_invalid_mobile_returns_422(async_client: AsyncClient):
    """A badly-formatted phone number should yield a 422 Unprocessable Entity."""
    response = await async_client.post("/auth/get_otp", json={"mobile_number": "not-a-phone"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_otp_missing_body_returns_422(async_client: AsyncClient):
    response = await async_client.post("/auth/get_otp", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/register  - Step 1: create inactive account, send OTP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_new_user_returns_201(async_client: AsyncClient, session: AsyncSession):
    """Registering with a fresh mobile number should create an inactive account (HTTP 201).
    No OTP is required in the request body; an OTP is sent after creation.
    """
    mobile = "+919000000001"
    with (
        patch("app.auth.routes.db_service.find_user_by_mobile_number", new=AsyncMock(return_value=None)),
        patch("app.auth.routes.db_service.find_stale_user_by_mobile_number", new=AsyncMock(return_value=None)),
        patch("app.auth.routes.generate_otp", new=MagicMock(return_value=TEST_OTP)),
        patch("app.auth.routes.db_service.add_otp_for_verification", new=AsyncMock()),
        patch("app.auth.routes.send_otp", new=AsyncMock()),
    ):
        response = await async_client.post("/auth/register", json={"mobile_number": mobile})

    assert response.status_code == 201
    data = response.json()
    assert "message" in data
    assert "expiry_minutes" in data
    # OTP echoed in development mode
    assert data["otp"] == TEST_OTP


@pytest.mark.asyncio
async def test_register_stale_account_reused_returns_201(async_client: AsyncClient, session: AsyncSession):
    """Re-registering with a mobile number that has a stale/unverified account
    should reuse that account and send a fresh OTP (HTTP 201).
    """
    mobile = "+919000000009"
    stale_user = User(mobile_number=mobile, is_active=False)
    session.add(stale_user)
    await session.commit()
    await session.refresh(stale_user)

    with (
        patch("app.auth.routes.db_service.find_user_by_mobile_number", new=AsyncMock(return_value=None)),
        patch("app.auth.routes.db_service.find_stale_user_by_mobile_number", new=AsyncMock(return_value=stale_user)),
        patch("app.auth.routes.generate_otp", new=MagicMock(return_value=TEST_OTP)),
        patch("app.auth.routes.db_service.add_otp_for_verification", new=AsyncMock()),
        patch("app.auth.routes.send_otp", new=AsyncMock()),
    ):
        response = await async_client.post("/auth/register", json={"mobile_number": mobile})

    assert response.status_code == 201
    data = response.json()
    assert "message" in data


@pytest.mark.asyncio
async def test_register_existing_active_user_returns_409(async_client: AsyncClient, session: AsyncSession):
    """Registering with a mobile number that already has an ACTIVE account should return HTTP 409."""
    mobile = "+919000000002"
    active_user = User(mobile_number=mobile, is_active=True)
    session.add(active_user)
    await session.commit()

    with patch("app.auth.routes.db_service.find_user_by_mobile_number", new=AsyncMock(return_value=active_user)):
        response = await async_client.post("/auth/register", json={"mobile_number": mobile})

    assert response.status_code == 409
    assert "already exists" in response.json()["message"]


@pytest.mark.asyncio
async def test_register_missing_mobile_returns_422(async_client: AsyncClient):
    """Omitting mobile_number should yield 422."""
    response = await async_client.post("/auth/register", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_mobile_returns_422(async_client: AsyncClient):
    """A badly-formatted phone number should yield 422."""
    response = await async_client.post("/auth/register", json={"mobile_number": "not-a-phone"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/verify_account  - Step 2: verify OTP, activate account
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_account_success_returns_200(async_client: AsyncClient, session: AsyncSession):
    """Verifying the correct OTP should activate the account and return JWT tokens."""
    mobile = "+919000000010"
    stale_user = User(mobile_number=mobile, is_active=False)
    session.add(stale_user)
    await session.commit()
    await session.refresh(stale_user)

    hashed = _hashed_test_otp()
    with (
        patch("app.auth.routes.db_service.get_otp_for_verification", new=AsyncMock(return_value=hashed)),
        patch("app.auth.routes.db_service.delete_otp_for_verification", new=AsyncMock()),
        patch("app.auth.routes.db_service.find_stale_user_by_mobile_number", new=AsyncMock(return_value=stale_user)),
        patch("app.auth.routes.db_service.activate_user", new=AsyncMock(return_value=stale_user)),
    ):
        response = await async_client.post(
            "/auth/verify_account",
            json={"mobile_number": mobile, "otp": TEST_OTP, "tnc_revision": TNC_REVISION},
        )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert "user_id" in data
    assert data["setup_profile"] is True
    assert data["tnc_accepted"] is True
    # Role claim must be embedded in both tokens (new users have no role → "customer")
    access_payload = decode_token(data["access_token"])
    assert access_payload["role"] == "customer"
    refresh_payload = decode_token(data["refresh_token"])
    assert refresh_payload["role"] == "customer"


@pytest.mark.asyncio
async def test_verify_account_invalid_otp_returns_400(async_client: AsyncClient):
    """A wrong OTP should return 400 and leave the account inactive."""
    hashed = _hashed_test_otp()  # hashed for TEST_OTP, but we send "000000"
    with patch("app.auth.routes.db_service.get_otp_for_verification", new=AsyncMock(return_value=hashed)):
        response = await async_client.post(
            "/auth/verify_account",
            json={"mobile_number": VALID_MOBILE, "otp": "000000", "tnc_revision": TNC_REVISION},
        )

    assert response.status_code == 400
    assert "Invalid" in response.json()["message"]


@pytest.mark.asyncio
async def test_verify_account_expired_otp_returns_400(async_client: AsyncClient):
    """If no OTP record exists (expired or never generated) the endpoint returns 400."""
    with patch("app.auth.routes.db_service.get_otp_for_verification", new=AsyncMock(return_value=None)):
        response = await async_client.post(
            "/auth/verify_account",
            json={"mobile_number": VALID_MOBILE, "otp": TEST_OTP, "tnc_revision": TNC_REVISION},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_verify_account_no_stale_account_returns_404(async_client: AsyncClient):
    """If the OTP is valid but no pending (stale) account exists the endpoint returns 404."""
    hashed = _hashed_test_otp()
    with (
        patch("app.auth.routes.db_service.get_otp_for_verification", new=AsyncMock(return_value=hashed)),
        patch("app.auth.routes.db_service.delete_otp_for_verification", new=AsyncMock()),
        patch("app.auth.routes.db_service.find_stale_user_by_mobile_number", new=AsyncMock(return_value=None)),
    ):
        response = await async_client.post(
            "/auth/verify_account",
            json={"mobile_number": VALID_MOBILE, "otp": TEST_OTP, "tnc_revision": TNC_REVISION},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_verify_account_missing_body_returns_422(async_client: AsyncClient):
    response = await async_client.post(
        "/auth/verify_account", json={"mobile_number": VALID_MOBILE, "otp": "", "tnc_revision": TNC_REVISION}
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/login  - login an existing ACTIVE account
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_existing_user_returns_200(async_client: AsyncClient, session: AsyncSession):
    """Logging in with an existing *active* account should return HTTP 200."""
    mobile = "+919000000003"
    user = User(mobile_number=mobile, is_active=True)
    session.add(user)
    await session.commit()

    hashed = _hashed_test_otp()
    with (
        patch("app.auth.routes.db_service.get_otp_for_verification", new=AsyncMock(return_value=hashed)),
        patch("app.auth.routes.db_service.delete_otp_for_verification", new=AsyncMock()),
    ):
        response = await async_client.post("/auth/login", json={"mobile_number": mobile, "otp": TEST_OTP})

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert "user_id" in data
    # Role claim must be present; user has no assigned role → defaults to "customer"
    access_payload = decode_token(data["access_token"])
    assert access_payload["role"] == "customer"


@pytest.mark.asyncio
async def test_login_non_existing_user_returns_404(async_client: AsyncClient):
    """Logging in with a number that has no active account should return HTTP 404."""
    hashed = _hashed_test_otp()
    with (
        patch("app.auth.routes.db_service.get_otp_for_verification", new=AsyncMock(return_value=hashed)),
        patch("app.auth.routes.db_service.delete_otp_for_verification", new=AsyncMock()),
    ):
        response = await async_client.post(
            "/auth/login",
            json={"mobile_number": "+919000000004", "otp": TEST_OTP, "tnc_revision": TNC_REVISION},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_login_invalid_otp_returns_400(async_client: AsyncClient):
    """Providing a wrong OTP should yield HTTP 400."""
    hashed = _hashed_test_otp()  # hashed for TEST_OTP, but we send "000000"
    with (
        patch("app.auth.routes.db_service.get_otp_for_verification", new=AsyncMock(return_value=hashed)),
        patch("app.auth.routes.db_service.delete_otp_for_verification", new=AsyncMock()),
    ):
        response = await async_client.post(
            "/auth/login",
            json={"mobile_number": VALID_MOBILE, "otp": "000000", "tnc_revision": TNC_REVISION},
        )

    assert response.status_code == 400
    assert "Invalid" in response.json()["message"]


@pytest.mark.asyncio
async def test_login_no_otp_generated_returns_400(async_client: AsyncClient):
    """If no OTP was generated for this number the endpoint should return 400."""
    with patch("app.auth.routes.db_service.get_otp_for_verification", new=AsyncMock(return_value=None)):
        response = await async_client.post("/auth/login", json={"mobile_number": VALID_MOBILE, "otp": TEST_OTP})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_wrong_body_returns_422(async_client: AsyncClient):
    response = await async_client.post("/auth/login", json={"mobile_number": VALID_MOBILE, "otp": ""})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/refresh_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_token_success(async_client: AsyncClient, session: AsyncSession):
    """A valid refresh token should yield new access + refresh tokens (201)."""
    mobile = "+919000000005"
    user = User(mobile_number=mobile, is_active=True)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    refresh_token = create_access_token(str(user.id), exp=settings.JWT_REFRESH_EXPIRY_TIME, refresh=True)

    with (
        patch("app.auth.security.token_in_blacklist", new=AsyncMock(return_value=False)),
        patch("app.auth.routes.db_service.add_jti_to_blacklist", new=AsyncMock()),
    ):
        response = await async_client.post(
            "/auth/refresh_token",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )

    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    # Role must be re-embedded on refresh; user has no role → "customer"
    access_payload = decode_token(data["access_token"])
    assert access_payload["role"] == "customer"


@pytest.mark.asyncio
async def test_refresh_token_with_access_token_fails(async_client: AsyncClient, session: AsyncSession):
    """Supplying an *access* token where a refresh token is expected must fail."""
    mobile = "+919000000006"
    user = User(mobile_number=mobile, is_active=True)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    access_token = create_access_token(str(user.id))

    with patch("app.auth.security.token_in_blacklist", new=AsyncMock(return_value=False)):
        response = await async_client.post(
            "/auth/refresh_token",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # RefreshTokenRequired → registered error handler → 403
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_refresh_token_missing_header_fails(async_client: AsyncClient):
    response = await async_client.post("/auth/refresh_token")
    # TokenBearer overrides HTTPBearer's 403 default with a 401 for all auth errors
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_success(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    """Logging out with a valid token should return 200."""
    with (
        patch("app.auth.security.token_in_blacklist", new=AsyncMock(return_value=False)),
        patch("app.auth.routes.db_service.add_jti_to_blacklist", new=AsyncMock()),
    ):
        response = await async_client.post("/auth/logout", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["message"] == "Logged Out Successfully"


@pytest.mark.asyncio
async def test_logout_no_token_fails(async_client: AsyncClient):
    """Calling /auth/logout without a token should return a 4xx error."""
    response = await async_client.post("/auth/logout")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_logout_blacklisted_token_fails(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    """If the token is already blacklisted the endpoint should reject it."""
    with patch("app.auth.security.token_in_blacklist", new=AsyncMock(return_value=True)):
        response = await async_client.post("/auth/logout", headers=auth_headers)
    assert response.status_code in (401, 403)


import uuid

from fastapi import HTTPException
from jwt import ExpiredSignatureError, InvalidTokenError

from app.auth.security import AccessTokenBearer, RefreshTokenBearer, TokenBearer, encrypt, get_current_user
from app.core.errors import AccessTokenRequired, InvalidToken, RefreshTokenRequired


@pytest.mark.asyncio
async def test_token_bearer_edge_cases():
    bearer = TokenBearer()

    # 1. Missing credentials
    mock_request = MagicMock()
    with patch("app.auth.security.HTTPBearer.__call__", return_value=None):
        with pytest.raises(HTTPException) as exc:
            await bearer(mock_request)
        assert exc.value.status_code == 401

    # 2. Expired signature
    with (
        patch("app.auth.security.HTTPBearer.__call__", return_value=MagicMock(credentials="expired")),
        patch("app.auth.security.decode_token", side_effect=ExpiredSignatureError("Signature has expired")),
    ):
        with pytest.raises(HTTPException) as exc:
            await bearer(mock_request)
        assert exc.value.status_code == 401

    # 3. JWTError
    with (
        patch("app.auth.security.HTTPBearer.__call__", return_value=MagicMock(credentials="bad_token")),
        patch("app.auth.security.decode_token", side_effect=InvalidTokenError("Invalid token")),
    ):
        with pytest.raises(HTTPException) as exc:
            await bearer(mock_request)
        assert exc.value.status_code == 401


def test_bearer_token_type_checks():
    # 4. AccessTokenRequired
    access_bearer = AccessTokenBearer()
    with pytest.raises(AccessTokenRequired):
        access_bearer.verify_token_data({"refresh": True})

    # 5. RefreshTokenRequired
    refresh_bearer = RefreshTokenBearer()
    with pytest.raises(RefreshTokenRequired):
        refresh_bearer.verify_token_data({"refresh": False})


@pytest.mark.asyncio
async def test_get_current_user_not_found(session: AsyncSession):
    # 6. User not found in db
    with pytest.raises(InvalidToken):
        await get_current_user({"sub": str(uuid.uuid4())}, session)


def test_encrypt_push_token():
    # 7. Test encrypt fingerprinting helper
    token = "my_push_token"  # noqa: S105
    res1 = encrypt(token)
    res2 = encrypt(token)
    assert res1 == res2
    assert isinstance(res1, str)


# ---------------------------------------------------------------------------
# Role claim in JWT tokens
# ---------------------------------------------------------------------------


def test_create_access_token_embeds_role_customer_by_default():
    """create_access_token without explicit role defaults to 'customer'."""
    import uuid as _uuid

    token = create_access_token(str(_uuid.uuid4()))
    payload = decode_token(token)
    assert payload["role"] == "customer"


def test_create_access_token_embeds_explicit_role():
    """create_access_token embeds whatever role is passed."""
    import uuid as _uuid

    for role in ("sales", "operations", "marketing", "admin"):
        token = create_access_token(str(_uuid.uuid4()), role=role)
        payload = decode_token(token)
        assert payload["role"] == role, f"Expected role={role!r} in token"


def test_refresh_token_carries_role():
    """Refresh tokens must also carry the role claim."""
    import uuid as _uuid

    token = create_access_token(str(_uuid.uuid4()), refresh=True, role="sales")
    payload = decode_token(token)
    assert payload["role"] == "sales"
    assert payload["refresh"] is True


@pytest.mark.asyncio
async def test_login_embeds_sales_role_in_token(async_client: AsyncClient, session: AsyncSession):
    """When a user has the 'sales' role assigned, the JWT must contain role='sales'."""
    mobile = "+919000000020"
    user = User(mobile_number=mobile, is_active=True)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    # Assign sales role
    await rbac_db_service.assign_role(session, user.id, UserRole.SALES)
    await session.commit()

    hashed = _hashed_test_otp()
    with (
        patch("app.auth.routes.db_service.get_otp_for_verification", new=AsyncMock(return_value=hashed)),
        patch("app.auth.routes.db_service.delete_otp_for_verification", new=AsyncMock()),
    ):
        response = await async_client.post("/auth/login", json={"mobile_number": mobile, "otp": TEST_OTP})

    assert response.status_code == 200
    data = response.json()
    payload = decode_token(data["access_token"])
    assert payload["role"] == "sales"


@pytest.mark.asyncio
async def test_login_embeds_admin_role_for_is_admin_flag(async_client: AsyncClient, session: AsyncSession):
    """A user with is_admin=True must get role='admin' regardless of role assignments."""
    mobile = "+919000000021"
    user = User(mobile_number=mobile, is_active=True, is_admin=True)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    hashed = _hashed_test_otp()
    with (
        patch("app.auth.routes.db_service.get_otp_for_verification", new=AsyncMock(return_value=hashed)),
        patch("app.auth.routes.db_service.delete_otp_for_verification", new=AsyncMock()),
    ):
        response = await async_client.post("/auth/login", json={"mobile_number": mobile, "otp": TEST_OTP})

    assert response.status_code == 200
    data = response.json()
    payload = decode_token(data["access_token"])
    assert payload["role"] == "admin"


@pytest.mark.asyncio
async def test_login_embeds_operations_role_in_token(async_client: AsyncClient, session: AsyncSession):
    """A user with the 'operations' role must get role='operations' in the JWT."""
    mobile = "+919000000022"
    user = User(mobile_number=mobile, is_active=True)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    await rbac_db_service.assign_role(session, user.id, UserRole.OPERATIONS)
    await session.commit()

    hashed = _hashed_test_otp()
    with (
        patch("app.auth.routes.db_service.get_otp_for_verification", new=AsyncMock(return_value=hashed)),
        patch("app.auth.routes.db_service.delete_otp_for_verification", new=AsyncMock()),
    ):
        response = await async_client.post("/auth/login", json={"mobile_number": mobile, "otp": TEST_OTP})

    assert response.status_code == 200
    payload = decode_token(response.json()["access_token"])
    assert payload["role"] == "operations"


@pytest.mark.asyncio
async def test_refresh_token_re_fetches_role_from_db(async_client: AsyncClient, session: AsyncSession):
    """Token refresh must re-fetch the role from the DB so that role changes
    take effect on the next refresh, rather than perpetuating a stale role.
    """
    mobile = "+919000000023"
    user = User(mobile_number=mobile, is_active=True)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    # Issue a refresh token that originally carried role="customer"
    refresh_token = create_access_token(
        str(user.id), exp=settings.JWT_REFRESH_EXPIRY_TIME, refresh=True, role="customer"
    )

    # Now assign sales role (simulates an admin promoting the user after their last login)
    await rbac_db_service.assign_role(session, user.id, UserRole.SALES)
    await session.commit()

    with (
        patch("app.auth.security.token_in_blacklist", new=AsyncMock(return_value=False)),
        patch("app.auth.routes.db_service.add_jti_to_blacklist", new=AsyncMock()),
    ):
        response = await async_client.post(
            "/auth/refresh_token",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )

    assert response.status_code == 201
    new_payload = decode_token(response.json()["access_token"])
    # Must reflect the newly assigned role, not the stale "customer" from the old token
    assert new_payload["role"] == "sales"
