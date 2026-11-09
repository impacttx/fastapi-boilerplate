"""
Unit tests for the ``/user`` endpoints.

Authenticated routes depend on:
  * A valid JWT token  (produced by ``auth_headers`` / ``auth_headers_tnc``)
  * ``token_in_blacklist`` returning ``False``       (patched per test)
  * ``get_current_user`` resolving the user from the test DB  (uses test session)
"""

from io import BytesIO
from unittest.mock import AsyncMock, patch

from httpx2 import AsyncClient
import pytest

from app.auth.models import User
from app.core.models import TermsAndConditions

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_NO_BLACKLIST = patch("app.auth.security.token_in_blacklist", new=AsyncMock(return_value=False))


# ---------------------------------------------------------------------------
# POST /user/tnc  - accept terms & conditions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_tnc_success(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    tnc_record: TermsAndConditions,
):
    """Accepting an existing TnC revision should return 200."""
    with _NO_BLACKLIST:
        response = await async_client.post(
            "/user/tnc",
            json={"revision": "v1.0", "accepted": True},
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


@pytest.mark.asyncio
async def test_accept_tnc_not_found_returns_404(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    """If there is no active TnC record the endpoint returns 404."""
    with (
        _NO_BLACKLIST,
        patch("app.user.routes.get_latest_active_terms", new=AsyncMock(return_value=None)),
    ):
        response = await async_client.post(
            "/user/tnc",
            json={"revision": "v1.0", "accepted": True},
            headers=auth_headers,
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_accept_tnc_not_accepted_returns_403(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    tnc_record: TermsAndConditions,
):
    """Submitting ``accepted=False`` should be rejected with 403."""
    with _NO_BLACKLIST:
        response = await async_client.post(
            "/user/tnc",
            json={"revision": "v1.0", "accepted": False},
            headers=auth_headers,
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_accept_tnc_missing_revision_returns_422(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    with _NO_BLACKLIST:
        response = await async_client.post(
            "/user/tnc",
            json={"accepted": True},  # no revision
            headers=auth_headers,
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_accept_tnc_unauthenticated_returns_4xx(async_client: AsyncClient):
    response = await async_client.post(
        "/user/tnc",
        json={"revision": "v1.0", "accepted": True},
    )
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /user/profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_profile_unauthenticated_returns_4xx(async_client: AsyncClient):
    response = await async_client.get("/user/profile")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_profile_without_tnc_returns_403(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    """A user who has not accepted TnC must be denied (403)."""
    with _NO_BLACKLIST:
        response = await async_client.get("/user/profile", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_profile_with_tnc_returns_200(
    async_client: AsyncClient,
    test_user_with_tnc: User,
    auth_headers_tnc: dict[str, str],
):
    """A user who accepted TnC should get their profile back."""
    with _NO_BLACKLIST:
        response = await async_client.get("/user/profile", headers=auth_headers_tnc)

    assert response.status_code == 200
    data = response.json()
    assert data["mobile_number"] == test_user_with_tnc.mobile_number
    assert "id" in data


# ---------------------------------------------------------------------------
# PUT /user/profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_profile_success(
    async_client: AsyncClient,
    test_user_with_tnc: User,
    auth_headers_tnc: dict[str, str],
):
    """Full profile update should return 202 with updated data."""
    payload = {
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "alice@example.com",
        "date_of_birth": "1990-06-15",
    }
    with _NO_BLACKLIST:
        response = await async_client.put("/user/profile", json=payload, headers=auth_headers_tnc)

    assert response.status_code == 202
    data = response.json()
    assert data["first_name"] == "Alice"
    assert data["last_name"] == "Smith"
    assert data["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_put_profile_without_tnc_returns_403(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    payload = {
        "first_name": "Alice",
        "last_name": "Smith",
        "date_of_birth": "1990-06-15",
    }
    with _NO_BLACKLIST:
        response = await async_client.put("/user/profile", json=payload, headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_put_profile_missing_required_field_returns_422(
    async_client: AsyncClient,
    test_user_with_tnc: User,
    auth_headers_tnc: dict[str, str],
):
    """PUT requires first_name, last_name and date_of_birth."""
    with _NO_BLACKLIST:
        response = await async_client.put(
            "/user/profile",
            json={"first_name": "Alice"},  # missing last_name and date_of_birth
            headers=auth_headers_tnc,
        )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /user/profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_profile_partial_update(
    async_client: AsyncClient,
    test_user_with_tnc: User,
    auth_headers_tnc: dict[str, str],
):
    """PATCH should return 202 (bio is not included in route response, only id/name/email fields)."""
    with _NO_BLACKLIST:
        response = await async_client.patch(
            "/user/profile",
            json={"bio": "Hello world"},
            headers=auth_headers_tnc,
        )

    assert response.status_code == 202
    # The patch route returns UserSchema which includes core fields; bio is accepted but
    # not echoed back in this response — verify the response is valid instead.
    assert "id" in response.json()
    assert "mobile_number" in response.json()


@pytest.mark.asyncio
async def test_patch_profile_email_update(
    async_client: AsyncClient,
    test_user_with_tnc: User,
    auth_headers_tnc: dict[str, str],
):
    with _NO_BLACKLIST:
        response = await async_client.patch(
            "/user/profile",
            json={"email": "patched@example.com"},
            headers=auth_headers_tnc,
        )
    assert response.status_code == 202
    assert response.json()["email"] == "patched@example.com"


@pytest.mark.asyncio
async def test_patch_profile_without_tnc_returns_403(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    with _NO_BLACKLIST:
        response = await async_client.patch(
            "/user/profile",
            json={"bio": "Test"},
            headers=auth_headers,
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_patch_profile_empty_body_still_returns_202(
    async_client: AsyncClient,
    test_user_with_tnc: User,
    auth_headers_tnc: dict[str, str],
):
    """Sending an empty body (no fields to update) must still succeed."""
    with _NO_BLACKLIST:
        response = await async_client.patch("/user/profile", json={}, headers=auth_headers_tnc)
    assert response.status_code == 202


# ---------------------------------------------------------------------------
# PUT /user/profile-picture
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_profile_picture_success(
    async_client: AsyncClient,
    test_user_with_tnc: User,
    auth_headers_tnc: dict[str, str],
):
    """Uploading a valid JPEG should return 200 with an image URL."""
    image_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # fake JPEG bytes
    with (
        _NO_BLACKLIST,
        patch("app.user.routes.put_object", new=AsyncMock()),
        patch("app.user.routes.settings") as mock_settings,
    ):
        # Ensure the test env is treated as NOT having S3 configured (use local storage)
        mock_settings.has_s3_configured.return_value = False
        mock_settings.STATIC_ASSETS_PATH = "/assets"
        response = await async_client.put(
            "/user/profile-picture",
            headers=auth_headers_tnc,
            files={"image": ("photo.jpg", BytesIO(image_bytes), "image/jpeg")},
        )

    assert response.status_code == 200
    assert "image_url" in response.json()


@pytest.mark.asyncio
async def test_upload_profile_picture_invalid_type_returns_422(
    async_client: AsyncClient,
    test_user_with_tnc: User,
    auth_headers_tnc: dict[str, str],
):
    """Uploading a non-image MIME type should be rejected (422)."""
    with _NO_BLACKLIST:
        response = await async_client.put(
            "/user/profile-picture",
            headers=auth_headers_tnc,
            files={"image": ("doc.pdf", BytesIO(b"%PDF"), "application/pdf")},
        )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /user/profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_profile_success(
    async_client: AsyncClient,
    test_user_with_tnc: User,
    auth_headers_tnc: dict[str, str],
):
    """Deleting own profile should return 200."""
    with _NO_BLACKLIST:
        response = await async_client.delete("/user/profile", headers=auth_headers_tnc)
    assert response.status_code == 200
    assert response.json()["status"] == "success"


# ---------------------------------------------------------------------------
# POST /user/account-report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_account_report_with_tnc(
    async_client: AsyncClient,
    test_user_with_tnc: User,
    auth_headers_tnc: dict[str, str],
):
    """Requesting an account report should return 202."""
    with _NO_BLACKLIST:
        response = await async_client.post("/user/account-report", headers=auth_headers_tnc)
    assert response.status_code == 202
    assert response.json()["status"] == "info"


@pytest.mark.asyncio
async def test_request_account_report_without_tnc_returns_403(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    with _NO_BLACKLIST:
        response = await async_client.post("/user/account-report", headers=auth_headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_profile_picture_s3_success(
    async_client: AsyncClient,
    test_user_with_tnc: User,
    auth_headers_tnc: dict[str, str],
):
    """Uploading a profile picture with S3 storage configured."""
    image_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    with (
        _NO_BLACKLIST,
        patch("app.user.routes.put_object", new=AsyncMock()) as mock_put,
        patch("app.user.routes.settings") as mock_settings,
    ):
        mock_settings.has_s3_configured.return_value = True
        mock_settings.DO_SPACES_CDN_ENDPOINT = "https://cdn.example.com"
        response = await async_client.put(
            "/user/profile-picture",
            headers=auth_headers_tnc,
            files={"image": ("photo.jpg", BytesIO(image_bytes), "image/jpeg")},
        )

    assert response.status_code == 200
    assert "image_url" in response.json()
    assert response.json()["image_url"].startswith("https://cdn.example.com")
    mock_put.assert_called_once()


@pytest.mark.asyncio
async def test_upload_profile_picture_various_filenames(
    async_client: AsyncClient,
    test_user_with_tnc: User,
    auth_headers_tnc: dict[str, str],
):
    """Test filename extraction logic with various cases (no dot, invalid extension)."""
    image_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100

    # 1. Filename has no dot
    with (
        _NO_BLACKLIST,
        patch("app.user.routes.put_object", new=AsyncMock()),
        patch("app.user.routes.settings") as mock_settings,
    ):
        mock_settings.has_s3_configured.return_value = False
        mock_settings.STATIC_ASSETS_PATH = "/assets"
        response = await async_client.put(
            "/user/profile-picture",
            headers=auth_headers_tnc,
            files={"image": ("photo_no_dot", BytesIO(image_bytes), "image/jpeg")},
        )
    assert response.status_code == 200

    # 2. Filename has invalid extension
    with (
        _NO_BLACKLIST,
        patch("app.user.routes.put_object", new=AsyncMock()),
        patch("app.user.routes.settings") as mock_settings,
    ):
        mock_settings.has_s3_configured.return_value = False
        mock_settings.STATIC_ASSETS_PATH = "/assets"
        response = await async_client.put(
            "/user/profile-picture",
            headers=auth_headers_tnc,
            files={"image": ("photo.invalid", BytesIO(image_bytes), "image/jpeg")},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_upload_profile_picture_without_tnc(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    """Uploading profile picture without accepting TnC should return 403."""
    image_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    with _NO_BLACKLIST:
        response = await async_client.put(
            "/user/profile-picture",
            headers=auth_headers,
            files={"image": ("photo.jpg", BytesIO(image_bytes), "image/jpeg")},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_patch_profile_all_fields(
    async_client: AsyncClient,
    test_user_with_tnc: User,
    auth_headers_tnc: dict[str, str],
):
    """PATCH with all profile patch fields specified."""
    payload = {
        "first_name": "UpdatedFirst",
        "last_name": "UpdatedLast",
        "email": "updated@example.com",
        "date_of_birth": "1995-12-25",
        "bio": "New Bio",
    }
    with _NO_BLACKLIST:
        response = await async_client.patch(
            "/user/profile",
            json=payload,
            headers=auth_headers_tnc,
        )
    assert response.status_code == 202
    data = response.json()
    assert data["first_name"] == "UpdatedFirst"
    assert data["last_name"] == "UpdatedLast"
    assert data["email"] == "updated@example.com"


def test_users_by_mobile_numbers_payload_validation():
    """Test validation constraints on UsersByMobileNumbersPayload schema."""
    from pydantic import ValidationError

    from app.user.schemas import UsersByMobileNumbersPayload

    # 1. Success with only mobile_numbers
    payload1 = UsersByMobileNumbersPayload(mobile_numbers=["+919876543210"])
    assert payload1.mobile_numbers == ["+919876543210"]

    # 2. Success with only user_ids
    import uuid

    payload2 = UsersByMobileNumbersPayload(user_ids=[uuid.uuid4()])
    assert isinstance(payload2.user_ids, list)
    assert len(payload2.user_ids) == 1

    # 3. ValidationError when neither is provided
    with pytest.raises(ValidationError) as exc_info:
        UsersByMobileNumbersPayload()
    assert "Either mobile_numbers, user_ids or both must be provided" in str(exc_info.value)
