"""Device registration routes for push notifications."""

from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from app.auth.db_service import find_active_devices_for_user, find_device_by_id
from app.auth.models import DevicePlatform, User, UserDevice
from app.auth.schemas import DeviceResponse, RegisterDeviceRequest, UpdateVoIPTokenRequest
from app.auth.security import get_current_user
from app.database import SessionDep

router = APIRouter(prefix="/devices", tags=["Devices"])

AUTH_REQUIRED = "Authentication required"


@router.post("/register", status_code=status.HTTP_200_OK)
async def register_device(
    db_session: SessionDep,
    request: RegisterDeviceRequest,
    user: User = Depends(get_current_user),
) -> DeviceResponse:
    """
    Register or update a device for push notifications.

    This endpoint should be called when the app starts or when push tokens are refreshed.
    If the device already exists, it will be updated with the new information.
    """
    logger.info(f"📱 [DEVICE] Registration request from user {user.id}")
    logger.info(
        f"📱 [DEVICE] device_id={request.device_id[:8]}... "
        f"platform={request.platform} "
        f"device_name={request.device_name}"
    )
    logger.info(
        f"📱 [DEVICE] expo_token={request.expo_push_token[:30] if request.expo_push_token else 'None'}... "
        f"voip_token={'Yes' if request.voip_push_token else 'No'}"
    )

    if not user.id:
        logger.warning("📱 [DEVICE] ❌ No user ID in request")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, AUTH_REQUIRED)

    # Validate platform
    try:
        platform = DevicePlatform(request.platform.lower())
    except ValueError as e:
        logger.error(f"📱 [DEVICE] ❌ Invalid platform: {request.platform}")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Invalid platform: {request.platform}. Must be 'ios' or 'android'",
        ) from e

    # Check if device already exists
    device = await find_device_by_id(db_session, request.device_id)

    if device:
        # Update existing device
        logger.info(f"📱 [DEVICE] Updating existing device {request.device_id[:8]}...")
        device.user_id = user.id
        device.platform = platform
        device.device_name = request.device_name
        device.expo_push_token = request.expo_push_token
        device.voip_push_token = request.voip_push_token
        device.fcm_token = request.fcm_token
        device.is_active = True
        device.last_active_at = datetime.now(tz=UTC)
        device.updated_at = datetime.now(tz=UTC)
        db_session.add(device)
        logger.info(f"📱 [DEVICE] ✅ Device {request.device_id[:8]}... updated for user {user.id}")
    else:
        # Create new device
        logger.info(f"📱 [DEVICE] Creating new device {request.device_id[:8]}...")
        device = UserDevice(
            user_id=user.id,
            device_id=request.device_id,
            platform=platform,
            device_name=request.device_name,
            expo_push_token=request.expo_push_token,
            voip_push_token=request.voip_push_token,
            fcm_token=request.fcm_token,
        )
        db_session.add(device)
        logger.info(f"📱 [DEVICE] ✅ New device {request.device_id[:8]}... registered for user {user.id}")

    await db_session.commit()
    return DeviceResponse(success=True, message="Device registered successfully")


@router.post("/voip-token", status_code=status.HTTP_200_OK)
async def update_voip_token(
    db_session: SessionDep,
    request: UpdateVoIPTokenRequest,
    user: User = Depends(get_current_user),
) -> DeviceResponse:
    """
    Update VoIP push token for a device (iOS only).

    VoIP tokens may change and need to be updated separately from device registration.
    """
    if not user.id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, AUTH_REQUIRED)

    device = await find_device_by_id(db_session, request.device_id)

    if not device or device.user_id != user.id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Device not found or does not belong to current user",
        )

    device.voip_push_token = request.voip_push_token
    device.updated_at = datetime.now(tz=UTC)
    db_session.add(device)
    await db_session.commit()

    logger.info(f"VoIP token updated for device {request.device_id[:8]}...")
    return DeviceResponse(success=True, message="VoIP token updated successfully")


@router.delete("/{device_id}", status_code=status.HTTP_200_OK)
async def unregister_device(
    device_id: str,
    db_session: SessionDep,
    user: User = Depends(get_current_user),
) -> DeviceResponse:
    """
    Unregister a device (on logout).

    This clears all push tokens and marks the device as inactive.
    """
    if not user.id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, AUTH_REQUIRED)

    device = await find_device_by_id(db_session, device_id)

    if not device or device.user_id != user.id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Device not found or does not belong to current user",
        )

    device.is_active = False
    device.expo_push_token = None
    device.voip_push_token = None
    device.fcm_token = None
    device.updated_at = datetime.now(tz=UTC)
    db_session.add(device)
    await db_session.commit()
    logger.info(f"Device {device_id[:8]}... unregistered for user {user.id}")

    return DeviceResponse(success=True, message="Device unregistered successfully")


@router.get("/", status_code=status.HTTP_200_OK)
async def list_user_devices(
    db_session: SessionDep,
    user: User = Depends(get_current_user),
) -> Sequence[UserDevice]:
    """
    List all registered devices for the current user.

    Useful for account management and debugging.
    """
    if not user.id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, AUTH_REQUIRED)

    return await find_active_devices_for_user(db_session, user.id)
