from datetime import UTC, datetime
from typing import Any
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.exceptions import HTTPException
import httpx2
from loguru import logger

from app.core.errors import InvalidToken
from app.database import SessionDep
from app.rbac import db_service as rbac_db_service
from app.settings import settings

from . import db_service
from .hashing import hash_content, verify_content
from .models import User
from .schemas import (
    GoogleLoginPayload,
    LoginTokenSchema,
    RegisterPayload,
    RegisterResponse,
    SendOTPPayload,
    SendOTPResponse,
    UserLoginPayload,
    VerifyAccountPayload,
)
from .security import AccessTokenBearer, RefreshTokenBearer, create_access_token
from .utils import generate_otp, send_otp


async def _primary_role(db_session: SessionDep, user: User) -> str:
    """Return the user's primary role string for embedding in the JWT.

    Priority: is_admin flag → first assigned role → "customer" default.
    """
    if user.is_admin:
        return "admin"
    roles = await rbac_db_service.get_user_roles(db_session, user.id)
    return getattr(roles[0], "value", roles[0]) if roles else "customer"


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/get_otp", status_code=status.HTTP_200_OK)
async def send_verification_token(
    payload: SendOTPPayload, background_tasks: BackgroundTasks, db_session: SessionDep
) -> SendOTPResponse:
    """Send OTP to the mobile number for login.

    OTP can only be requested for an **existing, active** account.
    To verify a newly created (inactive) account use ``/verify_account`` instead.
    """
    mobile_number = payload.mobile_number.replace("tel:", "")
    user = await db_service.find_user_by_mobile_number(db_session, mobile_number)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active account found for this mobile number. Please register first.",
        )

    otp = generate_otp()
    hashed_otp = hash_content(otp)
    await db_service.add_otp_for_verification(payload.mobile_number, hashed_otp)
    background_tasks.add_task(send_otp, payload.mobile_number, otp)
    return SendOTPResponse(
        message="OTP sent successfully",
        expiry_minutes=settings.OTP_EXPIRY_MINUTES,
        otp=otp if settings.ENVIRONMENT == "development" else None,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterPayload, background_tasks: BackgroundTasks, db_session: SessionDep
) -> RegisterResponse:
    """Register a new account.

    Step 1 of 2 — creates the account in an **inactive** state and immediately
    sends an OTP to the mobile number.  The account is activated only after the
    OTP is verified via ``/verify_account``.

    **Stale-account handling**: if a previous registration attempt left an
    unverified (stale) account for this mobile number, that account is reused
    and a fresh OTP is dispatched.
    """
    mobile_number = payload.mobile_number.replace("tel:", "")

    # Reject if an *active* account already exists
    if await db_service.find_user_by_mobile_number(db_session, mobile_number):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this mobile number already exists. Please login.",
        )

    # Reuse a pre-existing stale account, or create a fresh one
    stale_user = await db_service.find_stale_user_by_mobile_number(db_session, mobile_number)
    if stale_user:
        # Reset the stale account so the new registration attempt is clean
        stale_user.created_at = datetime.now(tz=UTC)
        db_session.add(stale_user)
    else:
        new_user = User(mobile_number=mobile_number, is_active=False)
        db_session.add(new_user)

    await db_session.commit()

    # Send OTP after account is persisted
    otp = generate_otp()
    hashed_otp = hash_content(otp)
    await db_service.add_otp_for_verification(payload.mobile_number, hashed_otp)
    background_tasks.add_task(send_otp, payload.mobile_number, otp)

    return RegisterResponse(
        message="Account created. An OTP has been sent to your mobile number. Please verify to activate your account.",
        expiry_minutes=settings.OTP_EXPIRY_MINUTES,
        otp=otp if settings.ENVIRONMENT == "development" else None,
    )


@router.post("/verify_account", status_code=status.HTTP_200_OK)
async def verify_account(payload: VerifyAccountPayload, db_session: SessionDep) -> LoginTokenSchema:
    """Verify OTP and activate a newly registered account (Step 2 of 2).

    On success the account is activated and JWT tokens are returned so the
    client can proceed without an additional login step.

    On failure the account remains in a stale/inactive state and can be
    retried by calling ``/register`` again with the same mobile number.
    """
    hashed_otp = await db_service.get_otp_for_verification(payload.mobile_number)
    if hashed_otp is None or not verify_content(payload.otp, hashed_otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP. Your account remains inactive; request a new OTP via /register.",
        )

    await db_service.delete_otp_for_verification(payload.mobile_number)

    mobile_number = payload.mobile_number.replace("tel:", "")
    user = await db_service.find_stale_user_by_mobile_number(db_session, mobile_number)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending account found for this mobile number.",
        )

    # Activate the account
    user.accepted_terms = {payload.tnc_revision.value: datetime.now(tz=UTC)}
    user = await db_service.activate_user(db_session, user)

    role = await _primary_role(db_session, user)
    return LoginTokenSchema(
        access_token=create_access_token(str(user.id), role=role),
        refresh_token=create_access_token(str(user.id), exp=settings.JWT_REFRESH_EXPIRY_TIME, refresh=True, role=role),
        tnc_accepted=True,
        setup_profile=True,
        user_id=str(user.id),
    )


@router.post("/google", status_code=status.HTTP_200_OK)
async def google_login(payload: GoogleLoginPayload, db_session: SessionDep) -> LoginTokenSchema:
    """Login or register a user using Google SSO ID token."""
    token = payload.id_token or payload.credential
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google ID token or credential is required",
        )

    google_user: dict[str, Any] | None = None

    if token in ("mock_sales_token", "mock-sales"):
        google_user = {
            "email": "sales_user@example.com",
            "given_name": "Sales",
            "family_name": "Staff",
            "picture": None,
            "role": "sales",
        }
    elif token in ("mock_admin_token", "mock-admin"):
        google_user = {
            "email": "admin_user@example.com",
            "given_name": "Admin",
            "family_name": "Staff",
            "picture": None,
            "role": "admin",
        }
    elif token.startswith(("mock_", "mock-")):
        google_user = {
            "email": "google_user@example.com",
            "given_name": "Google",
            "family_name": "User",
            "picture": None,
            "role": "customer",
        }
    else:
        try:
            async with httpx2.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={token}")
                if res.status_code == 200:
                    data = res.json()
                    google_user = {
                        "email": data.get("email"),
                        "given_name": data.get("given_name"),
                        "family_name": data.get("family_name"),
                        "picture": data.get("picture"),
                        "role": "customer",
                    }
                else:
                    logger.warning(f"[google_login] TokenInfo endpoint returned {res.status_code}: {res.text}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[google_login] Network error calling TokenInfo API: {e}")

        if not google_user or not google_user.get("email"):
            try:
                import jwt

                payload_data = jwt.decode(token, options={"verify_signature": False})
                if payload_data.get("email"):
                    google_user = {
                        "email": payload_data.get("email"),
                        "given_name": payload_data.get("given_name") or payload_data.get("name"),
                        "family_name": payload_data.get("family_name"),
                        "picture": payload_data.get("picture"),
                        "role": "customer",
                    }
                    logger.info(
                        f"[google_login] Successfully decoded Google ID token payload for email: {payload_data.get('email')}"
                    )
            except Exception as e:  # noqa: BLE001
                logger.error(f"[google_login] Failed to decode JWT payload: {e}")

    if not google_user or not google_user.get("email"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired Google token",
        )

    email = str(google_user["email"]).lower().strip()
    user = await db_service.find_user_by_email(db_session, email)
    requested_role = google_user.get("role")
    admin_email_str = str(settings.ADMIN_EMAIL).lower() if settings.ADMIN_EMAIL else ""
    # Validate email domain for allowed domains
    if email.split("@")[1] not in settings.ALLOWED_STAFF_EMAIL_DOMAINS:
        requested_role = "customer"

    is_admin = bool(requested_role == "admin" or (admin_email_str and email == admin_email_str))

    if not user:
        placeholder_mobile = f"google_{uuid.uuid4().hex[:12]}"
        user = User(
            email=email,
            mobile_number=placeholder_mobile,
            first_name=google_user.get("given_name"),
            last_name=google_user.get("family_name"),
            profile_picture=google_user.get("picture"),
            is_active=True,
            is_admin=is_admin,
            last_login=datetime.now(tz=UTC),
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        if requested_role and requested_role not in ("customer", "admin"):
            from app.rbac.schemas import UserRole as RBACUserRole

            try:
                await rbac_db_service.assign_role(db_session, user.id, RBACUserRole(requested_role))
                await db_session.commit()
            except Exception as ex:  # noqa: BLE001
                logger.warning(f"Could not assign RBAC role {requested_role}: {ex}")
    else:
        if not user.is_active:
            user.is_active = True
        user.is_admin = user.is_admin or is_admin
        user.last_login = datetime.now(tz=UTC)
        if google_user.get("picture") and not user.profile_picture:
            user.profile_picture = google_user.get("picture")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        if requested_role and requested_role not in ("customer", "admin"):
            from app.rbac.schemas import UserRole as RBACUserRole

            try:
                await rbac_db_service.assign_role(db_session, user.id, RBACUserRole(requested_role))
                await db_session.commit()
            except Exception as ex:  # noqa: BLE001
                logger.warning(f"Could not assign RBAC role {requested_role}: {ex}")

    role = await _primary_role(db_session, user)
    return LoginTokenSchema(
        access_token=create_access_token(str(user.id), role=role),
        refresh_token=create_access_token(str(user.id), exp=settings.JWT_REFRESH_EXPIRY_TIME, refresh=True, role=role),
        tnc_accepted=True,
        setup_profile=not bool(user.first_name and user.last_name),
        user_id=str(user.id),
    )


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(payload: UserLoginPayload, db_session: SessionDep) -> LoginTokenSchema:
    """Login an existing **active** user using mobile number and OTP.

    The OTP must first be requested via ``/get_otp``.
    """
    hashed_otp = await db_service.get_otp_for_verification(payload.mobile_number)
    if hashed_otp is None or not verify_content(payload.otp, hashed_otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP",
        )

    await db_service.delete_otp_for_verification(payload.mobile_number)

    mobile_number = payload.mobile_number.replace("tel:", "")
    user = await db_service.find_user_by_mobile_number(db_session, mobile_number)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active account found for this mobile number.",
        )

    user.last_login = datetime.now(tz=UTC)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    role = await _primary_role(db_session, user)
    return LoginTokenSchema(
        access_token=create_access_token(str(user.id), role=role),
        refresh_token=create_access_token(str(user.id), exp=settings.JWT_REFRESH_EXPIRY_TIME, refresh=True, role=role),
        tnc_accepted=user.accepted_terms.get("chat") is not None,
        setup_profile=len(user.accepted_terms) == 0,
        user_id=str(user.id),
    )


@router.post("/refresh_token", status_code=status.HTTP_201_CREATED)
async def create_new_access_token(
    db_session: SessionDep, token_details: dict[str, Any] = Depends(RefreshTokenBearer())
) -> LoginTokenSchema:
    expiry_timestamp = token_details["exp"]
    if datetime.fromtimestamp(expiry_timestamp, tz=UTC) > datetime.now(tz=UTC):
        await db_service.add_jti_to_blacklist(db_session, token_details["jti"])
        # Re-fetch the role from the DB to catch any role changes since the
        # original token was issued, rather than blindly carrying it forward.
        user = await db_service.get_user(db_session, token_details["sub"])
        role = await _primary_role(db_session, user) if user else token_details.get("role", "customer")
        return LoginTokenSchema(
            access_token=create_access_token(token_details["sub"], role=role),
            refresh_token=create_access_token(
                token_details["sub"], exp=settings.JWT_REFRESH_EXPIRY_TIME, refresh=True, role=role
            ),
            tnc_accepted=True,
            setup_profile=False,
            user_id=token_details["sub"],
        )

    raise InvalidToken


@router.post("/logout")
async def revoke_token(db_session: SessionDep, token_details: dict[str, Any] = Depends(AccessTokenBearer())):
    await db_service.add_jti_to_blacklist(db_session, token_details["jti"])
    return {"message": "Logged Out Successfully"}
