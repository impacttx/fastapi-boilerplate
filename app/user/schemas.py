from datetime import date
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.core.models import Revision


class TermAcceptancePayload(BaseModel):
    revision: Revision = Field(..., description="The version ID of the terms and conditions")
    accepted: bool = Field(..., description="Whether the terms were accepted or not")

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "revision": "v1.0",
                "accepted": True,
            }
        },
    )


class ProfileUpdatePayload(BaseModel):
    first_name: str = Field(
        ...,
        min_length=1,
        max_length=50,
    )
    last_name: str = Field(
        ...,
        min_length=1,
        max_length=50,
    )
    email: EmailStr | None = None
    date_of_birth: date = Field(
        description="Date of birth in YYYY-MM-DD format",
        examples=["1990-01-01"],
    )
    bio: str | None = Field(
        default=None,
        max_length=500,
        description="Short bio or status message",
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={
            "example": {
                "first_name": "Vinay",
                "last_name": "Sharma",
                "email": "username@example.com",
                "date_of_birth": "1990-01-01",
                "bio": "Software Developer",
            }
        }
    )


class ProfilePatchPayload(BaseModel):
    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    last_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    email: EmailStr | None = None
    date_of_birth: date | None = Field(
        default=None,
        description="Date of birth in YYYY-MM-DD format",
        examples=["1990-01-01"],
    )
    bio: str | None = Field(
        default=None,
        max_length=500,
        description="Short bio or status message",
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "first_name": "Bharat",
                "last_name": "Sharma",
                "email": "bharat@sharma.in",
                "date_of_birth": "1990-01-01",
                "bio": "~ Live and let live ❤️",
            }
        },
    )


class PushTokenPayload(BaseModel):
    push_token: str = Field(..., min_length=36, max_length=255, description="Push notification token to register")

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "push_token": "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]",
            }
        },
    )


class UserSchema(BaseModel):
    id: UUID
    mobile_number: str | None = None
    profile_picture: str | None = None
    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    last_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    email: EmailStr | None = None
    date_of_birth: date | None = Field(
        default=None,
        description="Date of birth in YYYY-MM-DD format",
        examples=["1990-01-01"],
    )
    bio: str | None = Field(
        default=None,
        max_length=500,
        description="Short bio or status message",
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "1234567890abcdef12345678",
                "mobile_number": "+919876543210",
                "first_name": "Bharat",
                "last_name": "Sharma",
                "email": "bharat@sharma.in",
                "date_of_birth": "1990-01-01",
                "profile_picture": "https://example.com/path/to/profile_picture.jpg",
                "bio": "~ Live and let live ❤️",
            }
        }
    )


class UsersByMobileNumbersPayload(BaseModel):
    mobile_numbers: list[str] | None = Field(
        default=None,
        description="List of E.164 formatted mobile numbers to look up",
        examples=[["+919876543210", "+911234567890"]],
    )
    user_ids: list[UUID] | None = Field(
        default=None,
        description="List of user IDs corresponding to the mobile numbers, if known",
        examples=[["1234567890abcdef12345678", "abcdef123456789012345678"]],
    )

    @model_validator(mode="before")
    @classmethod
    def validate_mobile_numbers(cls, values):
        mobile_numbers = values.get("mobile_numbers")
        user_ids = values.get("user_ids")
        if not mobile_numbers and not user_ids:
            raise ValueError("Either mobile_numbers, user_ids or both must be provided")
        return values
