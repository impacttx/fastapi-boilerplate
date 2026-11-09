from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict


class ItemCreate(BaseModel):
    title: str
    description: str | None = None
    is_completed: bool = False


class ItemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    is_completed: bool | None = None


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None = None
    is_completed: bool
    created_at: datetime
    updated_at: datetime | None = None
