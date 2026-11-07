"""Announcements, in-app notifications and leave applications."""
from __future__ import annotations

from ..extensions import db
from .base import TenantMixin, TimestampMixin, enum_column
from .enums import (
    AnnouncementCategory,
    AnnouncementScope,
    AnnouncementStatus,
    LeaveScope,
    LeaveStatus,
    NotificationKind,
)


class Announcement(TimestampMixin, db.Model):
    __tablename__ = "announcements"
    __table_args__ = (db.Index("ix_announcement_status_publish", "status", "publish_at"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("academic_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    author_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)
    category = enum_column(
        AnnouncementCategory, nullable=False, default=AnnouncementCategory.GENERAL
    )
    audience_scope = enum_column(
        AnnouncementScope, nullable=False, default=AnnouncementScope.ALL
    )
    school_class_id = db.Column(db.Integer, db.ForeignKey("school_classes.id", ondelete="SET NULL"))
    section_id = db.Column(db.Integer, db.ForeignKey("sections.id", ondelete="SET NULL"))
    publish_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    is_pinned = db.Column(db.Boolean, default=False, nullable=False)
    attachment_file_id = db.Column(
        db.Integer, db.ForeignKey("stored_files.id", ondelete="SET NULL")
    )
    status = enum_column(
        AnnouncementStatus, nullable=False, default=AnnouncementStatus.PUBLISHED
    )

    author = db.relationship("User")
    school_class = db.relationship("SchoolClass")
    section = db.relationship("Section")
    attachment = db.relationship("StoredFile")
    audience_rows = db.relationship(
        "AnnouncementAudience", back_populates="announcement", cascade="all, delete-orphan"
    )

    @property
    def is_live(self) -> bool:
        from .base import utcnow

        if self.status != AnnouncementStatus.PUBLISHED:
            return False
        now = utcnow()
        if self.publish_at and self.publish_at > now:
            return False
        if self.expires_at and self.expires_at < now:
            return False
        return True


class AnnouncementAudience(TimestampMixin, db.Model):
    """Optional fine-grained targeting beyond the simple scope."""

    __tablename__ = "announcement_audiences"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False
    )
    announcement_id = db.Column(
        db.Integer, db.ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False
    )
    target_type = db.Column(db.String(20), nullable=False)  # ROLE / CLASS / SECTION / STUDENT / GUARDIAN
    target_id = db.Column(db.Integer, nullable=True)

    announcement = db.relationship("Announcement", back_populates="audience_rows")


class Notification(TimestampMixin, db.Model):
    __tablename__ = "notifications"
    __table_args__ = (db.Index("ix_notification_user_read", "user_id", "read_at"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind = enum_column(NotificationKind, nullable=False, default=NotificationKind.SYSTEM)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.String(400), nullable=True)
    link_url = db.Column(db.String(255), nullable=True)
    entity_type = db.Column(db.String(40), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    read_at = db.Column(db.DateTime, nullable=True)

    @property
    def is_unread(self) -> bool:
        return self.read_at is None

    @property
    def tone(self) -> str:
        return {
            NotificationKind.ATTENDANCE: "warning",
            NotificationKind.RESULT: "success",
            NotificationKind.FEE: "danger",
            NotificationKind.HOMEWORK: "info",
            NotificationKind.ANNOUNCEMENT: "info",
            NotificationKind.TIMETABLE: "info",
        }.get(self.kind, "neutral")


class LeaveApplication(TimestampMixin, db.Model):
    __tablename__ = "leave_applications"
    __table_args__ = (
        db.Index("ix_leave_status", "school_id", "status"),
        db.CheckConstraint(
            "(scope = 'STUDENT' AND student_id IS NOT NULL AND staff_id IS NULL) OR "
            "(scope = 'STAFF' AND staff_id IS NOT NULL AND student_id IS NULL)",
            name="leave_scope_target",
        ),
        db.CheckConstraint("to_date >= from_date", name="leave_date_order"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("academic_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    scope = enum_column(LeaveScope, nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"))
    staff_id = db.Column(db.Integer, db.ForeignKey("staff_profiles.id", ondelete="CASCADE"))
    applicant_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    from_date = db.Column(db.Date, nullable=False)
    to_date = db.Column(db.Date, nullable=False)
    leave_type = db.Column(db.String(40), default="SICK", nullable=False)
    reason = db.Column(db.Text, nullable=False)
    attachment_file_id = db.Column(
        db.Integer, db.ForeignKey("stored_files.id", ondelete="SET NULL")
    )
    status = enum_column(LeaveStatus, nullable=False, default=LeaveStatus.PENDING)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_remarks = db.Column(db.String(255), nullable=True)

    student = db.relationship("Student")
    staff = db.relationship("StaffProfile")
    applicant = db.relationship("User", foreign_keys=[applicant_user_id])
    reviewer = db.relationship("User", foreign_keys=[reviewed_by_id])

    @property
    def days(self) -> int:
        return (self.to_date - self.from_date).days + 1

    @property
    def subject_label(self) -> str:
        if self.scope == LeaveScope.STUDENT and self.student:
            return self.student.full_name
        if self.staff:
            return self.staff.full_name
        return "—"
