"""Reusable model building blocks."""
from __future__ import annotations

from datetime import datetime, timezone

from ..extensions import db


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite has no tz-aware storage)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def enum_values(enum_cls):
    return [member.value for member in enum_cls]


def enum_column(enum_cls, **kwargs):
    """VARCHAR-backed enum with a CHECK constraint and readable values."""
    return db.Column(
        db.Enum(enum_cls, native_enum=False, length=32, values_callable=enum_values),
        **kwargs,
    )


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class TenantMixin:
    """Every tenant-owned row carries the school id.

    In this single-school release it is always 1, but having the column from
    day one keeps a future multi-tenant migration to a routing change rather
    than a schema rewrite.
    """

    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class SoftDeleteMixin:
    deleted_at = db.Column(db.DateTime, nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
