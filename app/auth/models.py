from datetime import UTC, date, datetime
import enum
import uuid

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Enum, Field, Relationship, SQLModel, UniqueConstraint, text


class DevicePlatform(str, enum.Enum):
    """Device platform types."""

    IOS = "ios"
    ANDROID = "android"


def now():
    return datetime.now(tz=UTC)


class User(SQLModel, table=True):
    # pyrefly: ignore [bad-override]
    __tablename__ = "users"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str | None = Field(default=None, unique=True, index=True)
    mobile_number: str | None = Field(default=None, unique=True, index=True)
    profile_picture: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    bio: str | None = None
    hashed_password: str | None = None
    is_active: bool = Field(default=False)
    is_admin: bool = Field(default=False)
    last_login: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            index=True,
            nullable=True,
        ),
    )
    date_of_birth: date | None = None
    accepted_terms: dict[str, datetime] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, index=True, nullable=False),
        description="Accepted terms and conditions, with revision as key and accepted time as value",
    )
    created_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            index=True,
            nullable=False,
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_onupdate=text("CURRENT_TIMESTAMP"),
            index=True,
            nullable=True,
        ),
    )
    last_activity: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True)))

    two_factor_codes: list[TwoFactorCode] = Relationship(back_populates="user")
    devices: list[UserDevice] = Relationship(back_populates="user")
    account_info_requests: list[AccountInfoRequest] = Relationship(back_populates="user")


class TwoFactorCode(SQLModel, table=True):
    # pyrefly: ignore [bad-override]
    __tablename__ = "two_factor_codes"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id")
    user: User = Relationship(back_populates="two_factor_codes")
    code: str = Field(index=True)  # Store hashed OTP
    expires_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            index=True,
            nullable=False,
        )
    )
    created_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            index=True,
            nullable=False,
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_onupdate=text("CURRENT_TIMESTAMP"),
            index=True,
            nullable=True,
        ),
    )


class Post(SQLModel, table=True):
    # pyrefly: ignore [bad-override]
    __tablename__ = "posts"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str
    slug: str = Field(unique=True, index=True)
    content: str  # TipTap JSON content stored as string
    published: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            index=True,
            nullable=False,
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_onupdate=text("CURRENT_TIMESTAMP"),
            index=True,
            nullable=True,
        ),
    )


class UserDevice(SQLModel, table=True):
    """User device registration for push notifications."""

    # pyrefly: ignore [bad-override]
    __tablename__ = "user_devices"  # pyright: ignore[reportAssignmentType]

    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    user: User = Relationship(back_populates="devices")

    # Device info
    device_id: str = Field(primary_key=True, index=True)  # Unique device identifier (e.g., UUID from the app)
    platform: DevicePlatform = Field(
        sa_column=Column(Enum(DevicePlatform, name="device_platform_enum"))
    )  # Device platform (iOS or Android)
    device_name: str | None = None

    # Push tokens
    expo_push_token: str | None = None  # Expo push token (for regular notifications)
    voip_push_token: str | None = None  # VoIP token (iOS only)
    fcm_token: str | None = None  # FCM token (Android)

    # Status
    is_active: bool = Field(default=True)  # Whether the device is active for receiving notifications
    last_active_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            index=True,
            nullable=False,
        ),
        description="Last time the device was active",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            index=True,
            nullable=False,
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_onupdate=text("CURRENT_TIMESTAMP"),
            index=True,
            nullable=True,
        ),
    )

    __table_args__ = (
        # Ensure a user can only have one active registration per device_id
        UniqueConstraint("user_id", "device_id", name="uq_user_device"),
    )


class AccountInfoRequest(SQLModel, table=True):
    # pyrefly: ignore [bad-override]
    __tablename__ = "account_info_requests"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id")
    user: User = Relationship(back_populates="account_info_requests")
    reason: str = Field(max_length=500)
    created_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            index=True,
            nullable=False,
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_onupdate=text("CURRENT_TIMESTAMP"),
            index=True,
            nullable=True,
        ),
    )


class MobileOTPRecord(SQLModel, table=True):
    # pyrefly: ignore [bad-override]
    """Stores hashed OTPs keyed by mobile number for sign-in/sign-up verification."""

    # pyrefly: ignore [bad-override]
    __tablename__ = "mobile_otp_records"  # pyright: ignore[reportAssignmentType]

    mobile_number: str = Field(primary_key=True, index=True)
    hashed_otp: str
    expires_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            index=True,
            nullable=False,
        )
    )
    created_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            index=True,
            nullable=False,
        ),
    )


class JWTBlacklist(SQLModel, table=True):
    """Revoked JWT token identifiers (jti).  Tokens in this table are rejected."""

    # pyrefly: ignore [bad-override]
    __tablename__ = "jwt_blacklist"  # pyright: ignore[reportAssignmentType]

    jti: str = Field(primary_key=True, index=True)
    expires_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            index=True,
            nullable=False,
        )
    )
    created_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            index=True,
            nullable=False,
        ),
    )
