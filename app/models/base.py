"""Common building blocks for Beanie documents."""

from datetime import datetime, timezone

from pydantic import Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Mixin adding created/updated timestamps to a document."""

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
