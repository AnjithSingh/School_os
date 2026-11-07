"""Academic structure: classes, sections, subjects and teaching allocations."""
from __future__ import annotations

from ..extensions import db
from .base import TenantMixin, TimestampMixin, enum_column
from .enums import Gender  # noqa: F401  (kept for import symmetry)


class SchoolClass(TimestampMixin, db.Model):
    __tablename__ = "school_classes"
    __table_args__ = (db.UniqueConstraint("school_id", "level", name="uq_class_school_level"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    level = db.Column(db.Integer, nullable=False)  # 6..10 in v1, extensible
    name = db.Column(db.String(40), nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    sections = db.relationship("Section", back_populates="school_class", lazy="selectin")

    @property
    def label(self) -> str:
        return self.name

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SchoolClass {self.name}>"


class Section(TimestampMixin, db.Model):
    """A section belongs to one academic session; 6-A is recreated each year."""

    __tablename__ = "sections"
    __table_args__ = (
        db.UniqueConstraint(
            "session_id", "school_class_id", "name", name="uq_section_session_class_name"
        ),
        db.Index("ix_section_session", "session_id"),
    )

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
    name = db.Column(db.String(10), nullable=False)
    room = db.Column(db.String(40), nullable=True)
    capacity = db.Column(db.Integer, default=45, nullable=False)
    class_teacher_id = db.Column(
        db.Integer, db.ForeignKey("staff_profiles.id", ondelete="SET NULL")
    )
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    session = db.relationship("AcademicSession", backref=db.backref("sections", lazy="dynamic"))
    school_class = db.relationship("SchoolClass", back_populates="sections")
    class_teacher = db.relationship("StaffProfile", foreign_keys=[class_teacher_id])
    enrollments = db.relationship("Enrollment", back_populates="section", lazy="dynamic")

    @property
    def label(self) -> str:
        return f"{self.school_class.name}-{self.name}" if self.school_class else self.name

    @property
    def student_count(self) -> int:
        from .enums import EnrollmentStatus

        return self.enrollments.filter_by(status=EnrollmentStatus.ACTIVE).count()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Section {self.label}>"


class Subject(TimestampMixin, db.Model):
    __tablename__ = "subjects"
    __table_args__ = (db.UniqueConstraint("school_id", "code", name="uq_subject_school_code"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    is_elective = db.Column(db.Boolean, default=False, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Subject {self.code}>"


class ClassSubject(TimestampMixin, db.Model):
    __tablename__ = "class_subjects"
    __table_args__ = (
        db.UniqueConstraint(
            "session_id", "school_class_id", "subject_id", name="uq_class_subject"
        ),
    )

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
    subject_id = db.Column(
        db.Integer, db.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    is_mandatory = db.Column(db.Boolean, default=True, nullable=False)
    default_max_marks = db.Column(db.Integer, default=100, nullable=False)

    subject = db.relationship("Subject")
    school_class = db.relationship("SchoolClass")


class SubjectAllocation(TimestampMixin, db.Model):
    __tablename__ = "subject_allocations"
    __table_args__ = (
        db.UniqueConstraint("section_id", "subject_id", name="uq_allocation_section_subject"),
        db.Index("ix_allocation_teacher", "teacher_id"),
    )

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
    periods_per_week = db.Column(db.Integer, default=5, nullable=False)

    section = db.relationship("Section", backref=db.backref("allocations", lazy="dynamic"))
    subject = db.relationship("Subject")
    teacher = db.relationship("StaffProfile", backref=db.backref("allocations", lazy="dynamic"))


class WorkingDay(TimestampMixin, db.Model):
    __tablename__ = "working_days"
    __table_args__ = (db.UniqueConstraint("session_id", "weekday", name="uq_working_day"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("academic_sessions.id", ondelete="CASCADE"), nullable=False
    )
    weekday = db.Column(db.Integer, nullable=False)  # 0=Monday
    is_working = db.Column(db.Boolean, default=True, nullable=False)
    is_half_day = db.Column(db.Boolean, default=False, nullable=False)

    session = db.relationship("AcademicSession", backref=db.backref("working_days", lazy="dynamic"))

    WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    @property
    def label(self) -> str:
        return self.WEEKDAY_NAMES[self.weekday]
