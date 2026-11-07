"""Homework, submissions and study materials."""
from __future__ import annotations

from ..extensions import db
from .base import TenantMixin, TimestampMixin, enum_column
from .enums import HomeworkStatus, SubmissionStatus


class Homework(TimestampMixin, db.Model):
    __tablename__ = "homework"
    __table_args__ = (db.Index("ix_homework_section_due", "section_id", "due_at"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("academic_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    section_id = db.Column(
        db.Integer, db.ForeignKey("sections.id", ondelete="CASCADE"), nullable=False
    )
    subject_id = db.Column(
        db.Integer, db.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    teacher_id = db.Column(
        db.Integer, db.ForeignKey("staff_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    assigned_on = db.Column(db.Date, nullable=False)
    due_at = db.Column(db.DateTime, nullable=True)
    attachment_file_id = db.Column(
        db.Integer, db.ForeignKey("stored_files.id", ondelete="SET NULL")
    )
    status = enum_column(HomeworkStatus, nullable=False, default=HomeworkStatus.PUBLISHED)
    max_marks = db.Column(db.Integer, nullable=True)

    section = db.relationship("Section", backref=db.backref("homework", lazy="dynamic"))
    subject = db.relationship("Subject")
    teacher = db.relationship("StaffProfile")
    attachment = db.relationship("StoredFile")
    submissions = db.relationship(
        "HomeworkSubmission", back_populates="homework", cascade="all, delete-orphan"
    )

    @property
    def is_overdue(self) -> bool:
        from .base import utcnow

        return bool(self.due_at and self.due_at < utcnow())


class HomeworkSubmission(TimestampMixin, db.Model):
    __tablename__ = "homework_submissions"
    __table_args__ = (
        db.UniqueConstraint("homework_id", "student_id", name="uq_submission_homework_student"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    homework_id = db.Column(
        db.Integer, db.ForeignKey("homework.id", ondelete="CASCADE"), nullable=False
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    file_id = db.Column(db.Integer, db.ForeignKey("stored_files.id", ondelete="SET NULL"))
    submitted_at = db.Column(db.DateTime, nullable=True)
    status = enum_column(SubmissionStatus, nullable=False, default=SubmissionStatus.SUBMITTED)
    remarks = db.Column(db.String(500), nullable=True)
    marks = db.Column(db.Integer, nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at = db.Column(db.DateTime, nullable=True)

    homework = db.relationship("Homework", back_populates="submissions")
    student = db.relationship("Student")
    file = db.relationship("StoredFile")


class StudyMaterial(TimestampMixin, db.Model):
    __tablename__ = "study_materials"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("academic_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    school_class_id = db.Column(
        db.Integer, db.ForeignKey("school_classes.id", ondelete="RESTRICT"), nullable=False
    )
    section_id = db.Column(db.Integer, db.ForeignKey("sections.id", ondelete="SET NULL"))
    subject_id = db.Column(
        db.Integer, db.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    file_id = db.Column(
        db.Integer, db.ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    is_published = db.Column(db.Boolean, default=True, nullable=False)

    school_class = db.relationship("SchoolClass")
    section = db.relationship("Section")
    subject = db.relationship("Subject")
    file = db.relationship("StoredFile")
