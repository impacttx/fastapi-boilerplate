"""
Unit tests for ``/devices`` endpoints.

Covers device registration, VoIP-token update, unregistration, and listing.
"""

from unittest.mock import AsyncMock, patch

from httpx2 import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import DevicePlatform, User, UserDevice

_NO_BLACKLIST = patch("app.auth.security.token_in_blacklist", new=AsyncMock(return_value=False))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEVICE_PAYLOAD = {
    "device_id": "TEST-DEVICE-001",
    "platform": "ios",
    "device_name": "iPhone 15 Pro",
    "expo_push_token": "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxxxx]",
    "voip_push_token": "abc123voip",
    "fcm_token": None,
}


async def _seed_device(session: AsyncSession, user: User, device_id: str = "TEST-DEVICE-001") -> UserDevice:
    """Insert a UserDevice row associated with *user*."""
    assert user.id is not None
    device = UserDevice(
        user_id=user.id,
        device_id=device_id,
        platform=DevicePlatform.IOS,
        device_name="Test Device",
        expo_push_token="ExponentPushToken[testtoken]",  # noqa: S106
    )
    session.add(device)
    await session.commit()
    await session.refresh(device)
    return device


# ---------------------------------------------------------------------------
# POST /devices/register
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_new_device_success(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    """Registering a brand-new device should return 200 with success=True."""
    with _NO_BLACKLIST:
        response = await async_client.post(
            "/devices/register",
            json=_DEVICE_PAYLOAD,
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "registered" in data["message"].lower()


@pytest.mark.asyncio
async def test_register_existing_device_updates_it(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    session: AsyncSession,
):
    """Re-registering an existing device (same device_id) should update it."""
    await _seed_device(session, test_user, device_id="EXISTING-001")

    updated_payload = {**_DEVICE_PAYLOAD, "device_id": "EXISTING-001", "device_name": "Updated Name"}

    with _NO_BLACKLIST:
        response = await async_client.post(
            "/devices/register",
            json=updated_payload,
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_register_android_device(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    payload = {
        "device_id": "ANDROID-DEVICE-001",
        "platform": "android",
        "device_name": "Pixel 9",
        "fcm_token": "fcm-token-abcdef",
    }
    with _NO_BLACKLIST:
        response = await async_client.post("/devices/register", json=payload, headers=auth_headers)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_register_device_invalid_platform_returns_400(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    """An unrecognised platform string should return HTTP 400."""
    invalid_payload = {**_DEVICE_PAYLOAD, "device_id": "BAD-PLATFORM-001", "platform": "windows"}
    with _NO_BLACKLIST:
        response = await async_client.post(
            "/devices/register",
            json=invalid_payload,
            headers=auth_headers,
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_device_unauthenticated_returns_4xx(async_client: AsyncClient):
    response = await async_client.post("/devices/register", json=_DEVICE_PAYLOAD)
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_register_device_missing_required_field_returns_422(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    """``platform`` is required; omitting it must fail with 422."""
    with _NO_BLACKLIST:
        response = await async_client.post(
            "/devices/register",
            json={"device_id": "MISSING-PLATFORM"},
            headers=auth_headers,
        )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /devices/voip-token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_voip_token_success(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    session: AsyncSession,
):
    """Updating the VoIP token on an existing device should return 200."""
    await _seed_device(session, test_user, device_id="VOIP-DEVICE-001")

    with _NO_BLACKLIST:
        response = await async_client.post(
            "/devices/voip-token",
            json={"device_id": "VOIP-DEVICE-001", "voip_push_token": "new-voip-token-xyz"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_update_voip_token_device_not_found_returns_404(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    with _NO_BLACKLIST:
        response = await async_client.post(
            "/devices/voip-token",
            json={"device_id": "NONEXISTENT-DEVICE", "voip_push_token": "token"},
            headers=auth_headers,
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_voip_token_other_users_device_returns_404(
    async_client: AsyncClient,
    test_user: User,
    test_user_with_tnc: User,
    auth_headers: dict[str, str],
    session: AsyncSession,
):
    """A user must not be able to update another user's device token."""
    # Seed device owned by test_user_with_tnc
    await _seed_device(session, test_user_with_tnc, device_id="OTHER-USER-DEVICE")

    with _NO_BLACKLIST:
        # auth_headers belongs to test_user - NOT the device owner
        response = await async_client.post(
            "/devices/voip-token",
            json={"device_id": "OTHER-USER-DEVICE", "voip_push_token": "token"},
            headers=auth_headers,
        )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# \DELETE /devices/{device_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unregister_device_success(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    session: AsyncSession,
):
    """Deleting own device should return 200 and mark it inactive."""
    await _seed_device(session, test_user, device_id="DELETE-ME-001")

    with _NO_BLACKLIST:
        response = await async_client.delete("/devices/DELETE-ME-001", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_unregister_device_not_found_returns_404(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    with _NO_BLACKLIST:
        response = await async_client.delete("/devices/GHOST-DEVICE", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unregister_other_users_device_returns_404(
    async_client: AsyncClient,
    test_user: User,
    test_user_with_tnc: User,
    auth_headers: dict[str, str],
    session: AsyncSession,
):
    await _seed_device(session, test_user_with_tnc, device_id="BELONGS-TO-OTHER")

    with _NO_BLACKLIST:
        response = await async_client.delete("/devices/BELONGS-TO-OTHER", headers=auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /devices/
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_devices_returns_active_devices(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    session: AsyncSession,
):
    """List endpoint should return only active devices for the current user."""
    await _seed_device(session, test_user, device_id="LIST-DEVICE-001")

    with _NO_BLACKLIST:
        response = await async_client.get("/devices/", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # The seeded device should appear (device_id is truncated to 8 chars + "...")
    assert any(d["device_id"].startswith("LIST-DEV") for d in data)


@pytest.mark.asyncio
async def test_list_devices_unauthenticated_returns_4xx(async_client: AsyncClient):
    response = await async_client.get("/devices/")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_device_routes_user_no_id(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    """If user.id is missing or None, endpoints should raise 401."""
    from app.auth.security import get_current_user
    from app.main import app

    # Create a dummy user without ID
    user_no_id = User(mobile_number="+910000000000", is_active=True)
    user_no_id.__dict__["id"] = None

    async def override_user():
        return user_no_id

    app.dependency_overrides[get_current_user] = override_user
    try:
        with _NO_BLACKLIST:
            # 1. Register device
            response = await async_client.post(
                "/devices/register",
                json=_DEVICE_PAYLOAD,
                headers=auth_headers,
            )
            assert response.status_code == 401

            # 2. VoIP token update
            response = await async_client.post(
                "/devices/voip-token",
                json={"device_id": "TEST-DEVICE-001", "voip_push_token": "token"},
                headers=auth_headers,
            )
            assert response.status_code == 401

            # 3. Unregister device
            response = await async_client.delete(
                "/devices/TEST-DEVICE-001",
                headers=auth_headers,
            )
            assert response.status_code == 401

            # 4. List user devices
            response = await async_client.get(
                "/devices/",
                headers=auth_headers,
            )
            assert response.status_code == 401
    finally:
        if get_current_user in app.dependency_overrides:
            del app.dependency_overrides[get_current_user]
