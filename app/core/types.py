"""Shared custom SQLAlchemy types."""

import uuid

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator


class UUIDListJSONB(TypeDecorator):
    """Stores a list of UUIDs as a JSONB array of strings."""

    impl = JSONB(none_as_null=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if not value:
            return None
        items = [str(item) for item in value if item is not None and str(item).strip() not in ("", "null", "None")]
        return items if items else None

    def process_result_value(self, value, dialect):
        if value is None or value == "null" or not value:
            return None
        if not isinstance(value, list):
            return None
        return [uuid.UUID(item) if not isinstance(item, uuid.UUID) else item for item in value]
