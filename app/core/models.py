from datetime import UTC, datetime
from enum import Enum
import uuid

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel, text


def now():
    return datetime.now(tz=UTC)


class Revision(str, Enum):
    V1_0 = "v1.0"
    V2_0 = "v2.0"


class TermsAndConditions(SQLModel, table=True):
    # pyrefly: ignore [bad-override]
    __tablename__ = "terms_and_conditions"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    revision: str = Field(
        index=True,
        unique=True,
        description="Unique identifier for the terms and conditions revision",
    )
    content: str  # The actual content of the terms and conditions
    created_by: uuid.UUID | None = Field(
        default=None,
        index=True,
        foreign_key="users.id",
        nullable=True,
        description="The user who created the terms and conditions",
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
    is_active: bool = Field(
        default=False,
        index=True,
        description="Indicates if the terms and conditions are currently published or in draft",
    )
