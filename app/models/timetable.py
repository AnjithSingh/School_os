"""Weekly timetable, periods and dated substitutions."""
from __future__ import annotations

from ..extensions import db
from .base import TenantMixin, TimestampMixin, enum_column
from .enums import ChangeType, PeriodKind, TimetableStatus


class Timetable(TimestampMixin, db.Model):
    __tablename__ = "timetables"
    __table_args__ = (
        db.UniqueConstraint("session_id", "name", name="uq_timetable_session_name"),
        db.Index("ix_timetable_session_status", "session_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("academic_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    name = db.Column(db.String(80), default="Master Timetable", nullable=False)
    status = enum_column(TimetableStatus, nullable=False, default=TimetableStatus.DRAFT)
    published_at = db.Column(db.DateTime, nullable=True)
    published_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    session = db.relationship("AcademicSession", backref=db.backref("timetables", lazy="dynamic"))
    periods = db.relationship(
        "TimetablePeriod",
        back_populates="timetable",
        cascade="all, delete-orphan",
        order_by="TimetablePeriod.sequence",
    )
    entries = db.relationship(
        "TimetableEntry", back_populates="timetable", cascade="all, delete-orphan", lazy="dynamic"
    )

    @property
    def class_periods(self):
        return [p for p in self.periods if p.kind == PeriodKind.CLASS]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Timetable {self.name} {self.status}>"


class TimetablePeriod(TimestampMixin, db.Model):
    __tablename__ = "timetable_periods"
    __table_args__ = (
        db.UniqueConstraint("timetable_id", "sequence", name="uq_period_timetable_sequence"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    timetable_id = db.Column(
        db.Integer, db.ForeignKey("timetables.id", ondelete="CASCADE"), nullable=False
    )
    sequence = db.Column(db.Integer, nullable=False)
    label = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    kind = enum_column(PeriodKind, nullable=False, default=PeriodKind.CLASS)

    timetable = db.relationship("Timetable", back_populates="periods")

    @property
    def is_break(self) -> bool:
        return self.kind != PeriodKind.CLASS


class TimetableEntry(TimestampMixin, db.Model):
    __tablename__ = "timetable_entries"
    __table_args__ = (
        db.UniqueConstraint(
            "timetable_id", "section_id", "weekday", "period_id", name="uq_entry_section_slot"
        ),
        # A teacher can only be in one room at a time.
        db.Index(
            "uq_entry_teacher_slot",
            "timetable_id",
            "teacher_id",
            "weekday",
            "period_id",
            unique=True,
            sqlite_where=db.text("teacher_id IS NOT NULL"),
        ),
        # A room can only host one class at a time.
        db.Index(
            "uq_entry_room_slot",
            "timetable_id",
            "room",
            "weekday",
            "period_id",
            unique=True,
            sqlite_where=db.text("room IS NOT NULL AND room != ''"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    timetable_id = db.Column(
        db.Integer, db.ForeignKey("timetables.id", ondelete="CASCADE"), nullable=False
    )
    section_id = db.Column(
        db.Integer, db.ForeignKey("sections.id", ondelete="CASCADE"), nullable=False
    )
    weekday = db.Column(db.Integer, nullable=False)
    period_id = db.Column(
        db.Integer, db.ForeignKey("timetable_periods.id", ondelete="CASCADE"), nullable=False
    )
    subject_id = db.Column(
        db.Integer, db.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    teacher_id = db.Column(db.Integer, db.ForeignKey("staff_profiles.id", ondelete="RESTRICT"))
    room = db.Column(db.String(40), nullable=True)

    timetable = db.relationship("Timetable", back_populates="entries")
    section = db.relationship("Section", backref=db.backref("timetable_entries", lazy="dynamic"))
    period = db.relationship("TimetablePeriod")
    subject = db.relationship("Subject")
    teacher = db.relationship("StaffProfile")


class TimetableChange(TimestampMixin, db.Model):
    __tablename__ = "timetable_changes"
    __table_args__ = (db.Index("ix_change_date_section", "date", "section_id"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    date = db.Column(db.Date, nullable=False)
    section_id = db.Column(
        db.Integer, db.ForeignKey("sections.id", ondelete="CASCADE"), nullable=False
    )
    original_entry_id = db.Column(
        db.Integer, db.ForeignKey("timetable_entries.id", ondelete="SET NULL")
    )
    change_type = enum_column(ChangeType, nullable=False)
    substitute_teacher_id = db.Column(
        db.Integer, db.ForeignKey("staff_profiles.id", ondelete="SET NULL")
    )
    new_room = db.Column(db.String(40), nullable=True)
    reason = db.Column(db.String(255), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    published_at = db.Column(db.DateTime, nullable=True)

    section = db.relationship("Section")
    original_entry = db.relationship("TimetableEntry")
    substitute_teacher = db.relationship("StaffProfile", foreign_keys=[substitute_teacher_id])
