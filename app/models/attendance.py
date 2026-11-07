"""Attendance records.

``uq(student_id, date)`` is the database-level guarantee that a student can
never have two attendance rows for the same day.
"""
from __future__ import annotations

from ..extensions import db
from .base import TimestampMixin, enum_column
from .enums import AttendanceStatus


class AttendanceRecord(TimestampMixin, db.Model):
    __tablename__ = "attendance_records"
    __table_args__ = (
        db.UniqueConstraint("student_id", "date", name="uq_attendance_student_date"),
        db.Index("ix_attendance_section_date", "section_id", "date", "status"),
        db.Index("ix_attendance_date", "date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="RESTRICT"), nullable=False
    )
    enrollment_id = db.Column(
        db.Integer, db.ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=False
    )
    section_id = db.Column(
        db.Integer, db.ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False
    )
    date = db.Column(db.Date, nullable=False, index=True)
    status = enum_column(AttendanceStatus, nullable=False)
    remarks = db.Column(db.String(255), nullable=True)
    marked_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    marked_at = db.Column(db.DateTime, nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    student = db.relationship("Student", backref=db.backref("attendance", lazy="dynamic"))
    enrollment = db.relationship("Enrollment", backref=db.backref("attendance", lazy="dynamic"))
    section = db.relationship("Section")
    marked_by = db.relationship("User", foreign_keys=[marked_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])

    @property
    def was_edited(self) -> bool:
        return bool(self.updated_by_id and self.updated_by_id != self.marked_by_id)

    @property
    def present_value(self) -> float:
        return {
            AttendanceStatus.PRESENT: 1.0,
            AttendanceStatus.LATE: 1.0,
            AttendanceStatus.HALF_DAY: 0.5,
            AttendanceStatus.EXCUSED: 1.0,
            AttendanceStatus.ABSENT: 0.0,
        }[self.status]
