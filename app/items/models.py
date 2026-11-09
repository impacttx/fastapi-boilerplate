from datetime import UTC, datetime
import uuid

from sqlmodel import Column, DateTime, Field, SQLModel, text


def now():
    return datetime.now(tz=UTC)


class Item(SQLModel, table=True):
    __tablename__ = "items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(index=True, max_length=255)
    description: str | None = Field(default=None)
    is_completed: bool = Field(default=False)
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
