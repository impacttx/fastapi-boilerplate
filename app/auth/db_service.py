from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.settings import settings

from .models import DevicePlatform, JWTBlacklist, MobileOTPRecord, User, UserDevice


async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    """Fetch a user by their ID."""
    statement = select(User).where(User.id == user_id)
    result = await session.exec(statement)
    return result.first()


async def find_user_by_mobile_number(session: AsyncSession, mobile_number: str) -> User | None:
    """Fetch an *active* user by their mobile number."""
    statement = select(User).where(User.mobile_number == mobile_number, User.is_active == True)
    result = await session.exec(statement)
    return result.first()


async def find_stale_user_by_mobile_number(session: AsyncSession, mobile_number: str) -> User | None:
    """Fetch a *stale* (inactive, unverified) user by their mobile number."""
    statement = select(User).where(User.mobile_number == mobile_number, User.is_active == False)
    result = await session.exec(statement)
    return result.first()


async def find_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Fetch a user by their email address."""
    statement = select(User).where(User.email == email)
    result = await session.exec(statement)
    return result.first()


async def activate_user(session: AsyncSession, user: User) -> User:
    """Mark a user as active (call after successful OTP verification)."""
    user.is_active = True
    user.last_login = datetime.now(tz=UTC)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user_last_activity(session: AsyncSession, user_id: UUID) -> None:
    """Update the last activity timestamp for a user."""
    if u := await get_user(session, user_id):
        u.last_activity = datetime.now(tz=UTC)
        session.add(u)
        await session.flush()


async def find_active_devices_for_user(
    session: AsyncSession,
    user_id: UUID,
    platform: DevicePlatform | None = None,
) -> Sequence[UserDevice]:
    """Find all active devices for a user, optionally filtered by platform."""
    statement = select(UserDevice).where(
        UserDevice.user_id == user_id,
        UserDevice.is_active == True,
    )
    if platform:
        statement = statement.where(UserDevice.platform == platform)

    return (await session.exec(statement)).all()


async def find_device_by_id(session: AsyncSession, device_id: str) -> UserDevice | None:
    """Find a device by its ID."""
    statement = select(UserDevice).where(UserDevice.device_id == device_id)
    result = await session.exec(statement)
    return result.first()


# ---------------------------------------------------------------------------
# JWT Blacklist helpers (database-backed)
# ---------------------------------------------------------------------------


async def add_jti_to_blacklist(session: AsyncSession, jti: str) -> None:
    """Add a JWT ID (jti) to the blacklist to invalidate the token.

    Stores the jti with its expiry so stale rows can be pruned later.
    """
    # Expire the blacklist entry after the max token lifetime so that the
    # table does not grow unbounded.
    expires_at = datetime.now(tz=UTC) + timedelta(
        minutes=max(settings.JWT_EXPIRY_TIME, settings.JWT_REFRESH_EXPIRY_TIME)
    )
    record = JWTBlacklist(jti=jti, expires_at=expires_at)
    session.add(record)
    await session.commit()


async def token_in_blacklist(jti: str) -> bool:
    """Check if a JWT ID (jti) is in the blacklist.

    NOTE: This implementation queries the database.  For high-traffic
    deployments, consider caching the result in Redis.
    """
    from app.database import async_session_maker  # local import to avoid circular dep

    async with async_session_maker() as session:
        now = datetime.now(tz=UTC)
        statement = select(JWTBlacklist).where(
            JWTBlacklist.jti == jti,
            JWTBlacklist.expires_at > now,
        )
        result = await session.exec(statement)
        return result.first() is not None


# ---------------------------------------------------------------------------
# OTP helpers (database-backed via MobileOTPRecord)
# ---------------------------------------------------------------------------


async def add_otp_for_verification(mobile_number: str, hashed_otp: str) -> None:
    """Store a hashed OTP for a mobile number, replacing any existing record."""
    from app.database import async_session_maker  # local import to avoid circular dep

    expires_at = datetime.now(tz=UTC) + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)
    async with async_session_maker() as session:
        # Remove any pre-existing OTP for this number (upsert pattern)
        await session.exec(delete(MobileOTPRecord).where(col(MobileOTPRecord.mobile_number) == mobile_number))
        record = MobileOTPRecord(mobile_number=mobile_number, hashed_otp=hashed_otp, expires_at=expires_at)
        session.add(record)
        await session.commit()


async def get_otp_for_verification(mobile_number: str) -> str | None:
    """Retrieve the hashed OTP for a mobile number if it has not expired."""
    from app.database import async_session_maker  # local import to avoid circular dep

    async with async_session_maker() as session:
        now = datetime.now(tz=UTC)
        statement = select(MobileOTPRecord).where(
            col(MobileOTPRecord.mobile_number) == mobile_number,
            MobileOTPRecord.expires_at > now,
        )
        result = await session.exec(statement)
        record = result.first()
        return record.hashed_otp if record else None


async def delete_otp_for_verification(mobile_number: str) -> None:
    """Delete the OTP record for a mobile number after successful verification."""
    from app.database import async_session_maker  # local import to avoid circular dep

    async with async_session_maker() as session:
        await session.exec(delete(MobileOTPRecord).where(col(MobileOTPRecord.mobile_number) == mobile_number))
        await session.commit()
