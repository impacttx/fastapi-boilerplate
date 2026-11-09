"""Unit tests for app.auth.db_service - covers the OTP, blacklist and device helpers."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch
import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.db_service import (
    activate_user,
    add_jti_to_blacklist,
    add_otp_for_verification,
    delete_otp_for_verification,
    find_active_devices_for_user,
    find_device_by_id,
    find_stale_user_by_mobile_number,
    find_user_by_mobile_number,
    get_otp_for_verification,
    get_user,
    token_in_blacklist,
    update_user_last_activity,
)
from app.auth.models import DevicePlatform, JWTBlacklist, User, UserDevice

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_async_session_maker(session: AsyncSession):
    """Return a callable that yields *session* as an async context manager."""

    @asynccontextmanager
    async def _cm():
        yield session

    return _cm


# ---------------------------------------------------------------------------
# get_user / find_user_by_mobile_number (use injected session)
# ---------------------------------------------------------------------------


async def test_get_user_returns_user(session: AsyncSession, test_user: User):
    assert test_user.id is not None
    found = await get_user(session, test_user.id)
    assert found is not None
    assert found.id == test_user.id


async def test_get_user_returns_none_for_missing(session: AsyncSession):
    result = await get_user(session, uuid.uuid4())
    assert result is None


async def test_find_user_by_mobile_number(session: AsyncSession, test_user: User):
    """find_user_by_mobile_number only returns *active* users."""
    assert test_user.mobile_number is not None
    assert test_user.is_active is True  # fixture sets this
    found = await find_user_by_mobile_number(session, test_user.mobile_number)
    assert found is not None
    assert found.mobile_number == test_user.mobile_number


async def test_find_user_by_mobile_number_ignores_stale(session: AsyncSession):
    """find_user_by_mobile_number should NOT return is_active=False (stale) users."""
    mobile = f"+155500{uuid.uuid4().int % 100000:05d}"
    stale = User(mobile_number=mobile, is_active=False)
    session.add(stale)
    await session.commit()
    result = await find_user_by_mobile_number(session, mobile)
    assert result is None


async def test_find_user_by_mobile_number_missing(session: AsyncSession):
    result = await find_user_by_mobile_number(session, "+19999999999")
    assert result is None


async def test_find_stale_user_by_mobile_number(session: AsyncSession):
    """find_stale_user_by_mobile_number should return is_active=False users."""
    mobile = f"+155501{uuid.uuid4().int % 100000:05d}"
    stale = User(mobile_number=mobile, is_active=False)
    session.add(stale)
    await session.commit()
    await session.refresh(stale)
    found = await find_stale_user_by_mobile_number(session, mobile)
    assert found is not None
    assert found.mobile_number == mobile
    assert found.is_active is False


async def test_find_stale_user_by_mobile_number_ignores_active(session: AsyncSession, test_user: User):
    """find_stale_user_by_mobile_number should NOT return active users."""
    assert test_user.is_active is True
    assert test_user.mobile_number is not None
    result = await find_stale_user_by_mobile_number(session, test_user.mobile_number)
    assert result is None


async def test_activate_user(session: AsyncSession):
    """activate_user should flip is_active to True and set last_login."""
    mobile = f"+155502{uuid.uuid4().int % 100000:05d}"
    stale = User(mobile_number=mobile, is_active=False)
    session.add(stale)
    await session.commit()
    await session.refresh(stale)

    activated = await activate_user(session, stale)
    assert activated.is_active is True
    assert activated.last_login is not None


# ---------------------------------------------------------------------------
# update_user_last_activity
# ---------------------------------------------------------------------------


async def test_update_user_last_activity(session: AsyncSession, test_user: User):
    assert test_user.id is not None
    before = test_user.last_activity
    # Sleep briefly so datetime.now() inside the function is guaranteed to differ
    await asyncio.sleep(0.01)
    await update_user_last_activity(session, test_user.id)
    # flush() inside the function writes changes to the DB within the transaction
    # so refresh() can read the updated value
    await session.refresh(test_user)
    assert test_user.last_activity is not None
    assert test_user.last_activity != before


async def test_update_user_last_activity_missing_user(session: AsyncSession):
    # Should not raise even if the user doesn't exist
    await update_user_last_activity(session, uuid.uuid4())


# ---------------------------------------------------------------------------
# find_active_devices_for_user / find_device_by_id
# ---------------------------------------------------------------------------


async def _seed_device(session: AsyncSession, user: User, platform=DevicePlatform.IOS, active=True) -> UserDevice:
    assert user.id is not None
    device = UserDevice(
        user_id=user.id,
        device_id=f"dev-{uuid.uuid4().hex[:8]}",
        platform=platform,
        is_active=active,
    )
    session.add(device)
    await session.commit()
    await session.refresh(device)
    return device


async def test_find_active_devices_no_filter(session: AsyncSession, test_user: User):
    assert test_user.id is not None
    d1 = await _seed_device(session, test_user, DevicePlatform.IOS)
    d2 = await _seed_device(session, test_user, DevicePlatform.ANDROID)
    result = await find_active_devices_for_user(session, test_user.id)
    ids = [d.device_id for d in result]
    assert d1.device_id in ids
    assert d2.device_id in ids


async def test_find_active_devices_with_platform_filter(session: AsyncSession, test_user: User):
    assert test_user.id is not None
    ios_dev = await _seed_device(session, test_user, DevicePlatform.IOS)
    await _seed_device(session, test_user, DevicePlatform.ANDROID)
    result = await find_active_devices_for_user(session, test_user.id, platform=DevicePlatform.IOS)
    assert all(d.platform == DevicePlatform.IOS for d in result)
    ids = [d.device_id for d in result]
    assert ios_dev.device_id in ids


async def test_find_active_devices_excludes_inactive(session: AsyncSession, test_user: User):
    assert test_user.id is not None
    inactive = await _seed_device(session, test_user, active=False)
    result = await find_active_devices_for_user(session, test_user.id)
    assert inactive.device_id not in [d.device_id for d in result]


async def test_find_device_by_id(session: AsyncSession, test_user: User):
    device = await _seed_device(session, test_user)
    found = await find_device_by_id(session, device.device_id)
    assert found is not None
    assert found.device_id == device.device_id


async def test_find_device_by_id_missing(session: AsyncSession):
    result = await find_device_by_id(session, "nonexistent-device")
    assert result is None


# ---------------------------------------------------------------------------
# add_jti_to_blacklist (uses the injected session, not async_session_maker)
# ---------------------------------------------------------------------------


async def test_add_jti_to_blacklist(session: AsyncSession):
    jti = f"jti-{uuid.uuid4().hex}"
    await add_jti_to_blacklist(session, jti)
    stmt = select(JWTBlacklist).where(JWTBlacklist.jti == jti)
    result = (await session.exec(stmt)).first()
    assert result is not None
    assert result.jti == jti


# ---------------------------------------------------------------------------
# token_in_blacklist (uses async_session_maker internally - mock it)
# ---------------------------------------------------------------------------


async def test_token_in_blacklist_returns_false_when_not_blacklisted(session: AsyncSession):
    """Mock async_session_maker to use the test session so no new connection is made."""
    jti = f"jti-{uuid.uuid4().hex}"
    with patch("app.database.async_session_maker", _make_async_session_maker(session)):
        result = await token_in_blacklist(jti)
    assert result is False


async def test_token_in_blacklist_returns_true_after_add(session: AsyncSession):
    jti = f"jti-{uuid.uuid4().hex}"
    await add_jti_to_blacklist(session, jti)
    await session.commit()

    with patch("app.database.async_session_maker", _make_async_session_maker(session)):
        result = await token_in_blacklist(jti)
    assert result is True


# ---------------------------------------------------------------------------
# OTP helpers (use async_session_maker internally - mock it)
# ---------------------------------------------------------------------------


async def test_add_get_delete_otp(session: AsyncSession):
    mobile = "+15550009999"
    raw_otp = "112233"

    from app.auth.hashing import hash_content

    hashed = hash_content(raw_otp)
    session_maker = _make_async_session_maker(session)

    with patch("app.database.async_session_maker", session_maker):
        await add_otp_for_verification(mobile, hashed)

    with patch("app.database.async_session_maker", session_maker):
        stored = await get_otp_for_verification(mobile)

    assert stored == hashed

    with patch("app.database.async_session_maker", session_maker):
        await delete_otp_for_verification(mobile)

    with patch("app.database.async_session_maker", session_maker):
        after_delete = await get_otp_for_verification(mobile)

    assert after_delete is None


async def test_add_otp_replaces_existing(session: AsyncSession):
    """Calling add_otp_for_verification twice should replace the record (no UniqueConstraint)."""
    mobile = "+15551118888"
    session_maker = _make_async_session_maker(session)

    with patch("app.database.async_session_maker", session_maker):
        await add_otp_for_verification(mobile, "hash-old")
        await add_otp_for_verification(mobile, "hash-new")

    with patch("app.database.async_session_maker", session_maker):
        stored = await get_otp_for_verification(mobile)

    assert stored == "hash-new"


async def test_get_otp_returns_none_when_not_stored(session: AsyncSession):
    session_maker = _make_async_session_maker(session)
    with patch("app.database.async_session_maker", session_maker):
        result = await get_otp_for_verification("+19998887777")
    assert result is None
