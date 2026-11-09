"""Role-Based Access Control models.

Roles: customer, sales, operations, marketing, admin
Per BRD Section 5.2 and 7.7
"""

from datetime import UTC, datetime
import uuid

from sqlalchemy import Column, DateTime, String, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel, text


def now():
    return datetime.now(tz=UTC)


class Role(SQLModel, table=True):
    """Role definition table."""

    # pyrefly: ignore [bad-override]
    __tablename__ = "roles"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(sa_column=Column(String(32), unique=True, nullable=False, index=True))
    description: str | None = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(
        default_factory=now,
        sa_column=Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False, index=True),
    )

    # Relationships
    user_roles: list[UserRoleAssignment] = Relationship(back_populates="role")


class UserRoleAssignment(SQLModel, table=True):
    """Many-to-many: users <-> roles."""

    # pyrefly: ignore [bad-override]
    __tablename__ = "user_role_assignments"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    role_id: uuid.UUID = Field(foreign_key="roles.id", index=True)
    assigned_by: uuid.UUID | None = Field(default=None, foreign_key="users.id", nullable=True, index=True)
    created_at: datetime = Field(
        default_factory=now,
        sa_column=Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False, index=True),
    )

    # Relationships
    role: Role = Relationship(back_populates="user_roles")

    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)
