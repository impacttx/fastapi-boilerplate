from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic_extra_types.phone_numbers import PhoneNumberValidator

from app.core.models import Revision


class SendOTPPayload(BaseModel):
    mobile_number: Annotated[str, PhoneNumberValidator(number_format="E164")] = Field(
        ...,
        description="Mobile number of the user to send OTP",
        examples=["+919876543210", "+14155552671"],
    )


class SendOTPResponse(BaseModel):
    message: str = Field(..., description="Message indicating the status of OTP sending")
    expiry_minutes: int = Field(
        default=5,
        description="Expiry time of the OTP in minutes",
        examples=[5, 10, 15],
    )
    # OTP is included only in development environment for testing purposes
    otp: str | None = Field(None, description="OTP sent to the user, only included in development environment")

    model_config: ClassVar[ConfigDict] = ConfigDict(
        title="SendOTPResponse",
        from_attributes=True,
        json_schema_extra={
            "example": {
                "message": "OTP sent successfully",
                "expiry_minutes": 5,
                "otp": "123456",  # Only for development purposes
            }
        },
    )


class RegisterPayload(BaseModel):
    """Payload for the first step of registration — just mobile number, no OTP."""

    mobile_number: Annotated[str, PhoneNumberValidator(number_format="E164")] = Field(
        ...,
        description="Mobile number to register",
        examples=["+919876543210", "+14155552671"],
    )
    model_config: ClassVar[ConfigDict] = ConfigDict(
        title="RegisterPayload",
        from_attributes=True,
        json_schema_extra={"example": {"mobile_number": "+919876543210"}},
    )


class RegisterResponse(BaseModel):
    """Response returned right after account creation — prompts the client to verify OTP."""

    message: str = Field(..., description="Status message")
    expiry_minutes: int = Field(
        default=5,
        description="Expiry time of the OTP in minutes",
    )
    # OTP included only in development for testing
    otp: str | None = Field(None, description="OTP sent to user (development only)")

    model_config: ClassVar[ConfigDict] = ConfigDict(
        title="RegisterResponse",
        from_attributes=True,
        json_schema_extra={
            "example": {
                "message": "Account created. OTP sent to your mobile number for verification.",
                "expiry_minutes": 5,
                "otp": None,
            }
        },
    )


class VerifyAccountPayload(BaseModel):
    """Payload for the OTP-verification step after registration."""

    mobile_number: Annotated[str, PhoneNumberValidator(number_format="E164")] = Field(
        ...,
        description="Mobile number used during registration",
        examples=["+919876543210"],
    )
    otp: str = Field(..., description="OTP received on the mobile number", min_length=1)
    tnc_revision: Revision = Field(
        ...,
        description="Revision of the terms and conditions accepted by the user",
        examples=["v1.0"],
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(
        title="VerifyAccountPayload",
        from_attributes=True,
        json_schema_extra={"example": {"mobile_number": "+919876543210", "otp": "123456", "tnc_revision": "v1.0"}},
    )


class UserLoginPayload(BaseModel):
    mobile_number: Annotated[str, PhoneNumberValidator(number_format="E164")] = Field(
        ...,
        description="Mobile number of the user",
        examples=["+919876543210", "+14155552671"],
    )
    otp: str = Field(..., description="OTP", min_length=1)

    model_config: ClassVar[ConfigDict] = ConfigDict(
        title="UserLoginPayload",
        from_attributes=True,
        json_schema_extra={"example": {"mobile_number": "+919876543210", "otp": "123456"}},
    )


class GoogleLoginPayload(BaseModel):
    id_token: str | None = Field(None, description="Google ID Token credential")
    credential: str | None = Field(None, description="Alias for Google ID Token credential")

    model_config: ClassVar[ConfigDict] = ConfigDict(
        title="GoogleLoginPayload",
        from_attributes=True,
        json_schema_extra={"example": {"id_token": "eyJhbGciOiJSUzI1NiIs..."}},
    )


class UserUpdatePayload(BaseModel):
    username: str | None = Field(None, description="Username for the user")
    display_name: str | None = Field(None, description="Display name for the user")

    model_config: ClassVar[ConfigDict] = ConfigDict(
        title="UserUpdatePayload",
        from_attributes=True,
        json_schema_extra={
            "example": {
                "username": "john_doe_updated",
                "display_name": "John Doe Updated",
            }
        },
    )


class LoginTokenSchema(BaseModel):
    access_token: str
    refresh_token: str
    tnc_accepted: bool = Field(
        default=False,
        description="Deprecated! Use setup_profile instead",
        examples=[True, False],
        deprecated=True,
    )
    setup_profile: bool = Field(
        default=True,
        description="Indicates whether the user needs to set up their profile",
        examples=[True, False],
    )
    user_id: str | None = Field(
        default=None,
        description="User ID of the logged-in user",
        examples=["60f7c0d5b4d1c2a5fc8e4b2a"],
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(
        title="LoginTokenSchema",
        from_attributes=True,
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "tnc_accepted": True,
                "setup_profile": False,
                "user_id": "60f7c0d5b4d1c2a5fc8e4b2a",
            }
        },
    )


# Device registration schemas
class RegisterDeviceRequest(BaseModel):
    """Request schema for registering a device for push notifications."""

    device_id: str = Field(..., description="Unique device identifier")
    platform: str = Field(..., description="Device platform: 'ios' or 'android'")
    device_name: str | None = Field(None, description="Human-readable device name")
    expo_push_token: str | None = Field(None, description="Expo push token for regular notifications")
    voip_push_token: str | None = Field(None, description="VoIP push token (iOS only)")
    fcm_token: str | None = Field(None, description="FCM token (Android)")

    model_config: ClassVar[ConfigDict] = ConfigDict(
        title="RegisterDeviceRequest",
        from_attributes=True,
        json_schema_extra={
            "example": {
                "device_id": "ABC123-DEVICE-UUID",
                "platform": "ios",
                "device_name": "iPhone 15 Pro",
                "expo_push_token": "ExponentPushToken[xxxxx]",
                "voip_push_token": "64_char_hex_voip_token_here",
            }
        },
    )


class UpdateVoIPTokenRequest(BaseModel):
    """Request schema for updating VoIP push token."""

    device_id: str = Field(..., description="Device ID to update")
    voip_push_token: str = Field(..., description="New VoIP push token")

    model_config: ClassVar[ConfigDict] = ConfigDict(
        title="UpdateVoIPTokenRequest",
        from_attributes=True,
        json_schema_extra={
            "example": {
                "device_id": "ABC123-DEVICE-UUID",
                "voip_push_token": "64_char_hex_voip_token_here",
            }
        },
    )


class DeviceResponse(BaseModel):
    """Response schema for device operations."""

    success: bool = Field(..., description="Operation success status")
    message: str = Field(..., description="Status message")

    model_config: ClassVar[ConfigDict] = ConfigDict(
        title="DeviceResponse",
        from_attributes=True,
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Device registered successfully",
            }
        },
    )
