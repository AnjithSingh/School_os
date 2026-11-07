"""People: staff, students, guardians and the relationships between them."""
from __future__ import annotations

from datetime import date

from ..extensions import db
from .base import SoftDeleteMixin, TenantMixin, TimestampMixin, enum_column
from .enums import (
    DocumentType,
    EnrollmentStatus,
    Gender,
    LinkStatus,
    StaffType,
    StudentStatus,
)


class StaffProfile(TimestampMixin, db.Model):
    __tablename__ = "staff_profiles"
    __table_args__ = (
        db.UniqueConstraint("user_id", name="uq_staff_user"),
        db.UniqueConstraint("school_id", "employee_code", name="uq_staff_employee_code"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    employee_code = db.Column(db.String(30), nullable=False)
    staff_type = enum_column(StaffType, nullable=False, default=StaffType.TEACHING)
    designation = db.Column(db.String(80), nullable=True)
    department = db.Column(db.String(80), nullable=True)
    qualification = db.Column(db.String(160), nullable=True)
    specialisation = db.Column(db.String(160), nullable=True)
    joining_date = db.Column(db.Date, nullable=True)
    employment_type = db.Column(db.String(30), default="FULL_TIME", nullable=False)
    employment_status = db.Column(db.String(20), default="ACTIVE", nullable=False)
    dob = db.Column(db.Date, nullable=True)
    gender = enum_column(Gender, nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    emergency_contact = db.Column(db.String(30), nullable=True)
    photo_file_id = db.Column(db.Integer, db.ForeignKey("stored_files.id", ondelete="SET NULL"))
    reports_to_id = db.Column(db.Integer, db.ForeignKey("staff_profiles.id", ondelete="SET NULL"))

    user = db.relationship("User", back_populates="staff_profile", foreign_keys=[user_id])
    reports_to = db.relationship("StaffProfile", remote_side=[id], foreign_keys=[reports_to_id])

    @property
    def is_teacher(self) -> bool:
        return self.staff_type == StaffType.TEACHING

    @property
    def full_name(self) -> str:
        return self.user.full_name if self.user else "—"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<StaffProfile {self.employee_code}>"


class Student(TimestampMixin, SoftDeleteMixin, db.Model):
    """Identity only. Class/section live on Enrollment (one per session)."""

    __tablename__ = "students"
    __table_args__ = (
        db.UniqueConstraint("school_id", "admission_no", name="uq_student_admission_no"),
        db.Index("ix_student_name", "last_name", "first_name"),
        db.Index("ix_student_status", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    admission_no = db.Column(db.String(30), nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    dob = db.Column(db.Date, nullable=True)
    gender = enum_column(Gender, nullable=True)
    blood_group = db.Column(db.String(8), nullable=True)
    photo_file_id = db.Column(db.Integer, db.ForeignKey("stored_files.id", ondelete="SET NULL"))

    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(80), nullable=True)
    state = db.Column(db.String(80), nullable=True)
    pincode = db.Column(db.String(12), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(160), nullable=True)

    emergency_name = db.Column(db.String(120), nullable=True)
    emergency_phone = db.Column(db.String(30), nullable=True)
    category = db.Column(db.String(40), nullable=True)
    admission_date = db.Column(db.Date, default=date.today, nullable=False)
    status = enum_column(StudentStatus, nullable=False, default=StudentStatus.ACTIVE)
    notes = db.Column(db.Text, nullable=True)

    user = db.relationship("User", back_populates="student", foreign_keys=[user_id])
    enrollments = db.relationship(
        "Enrollment",
        back_populates="student",
        lazy="selectin",
        order_by="Enrollment.id.desc()",
    )
    guardian_links = db.relationship(
        "GuardianStudentLink", back_populates="student", cascade="all, delete-orphan"
    )
    photo = db.relationship("StoredFile", foreign_keys=[photo_file_id])

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def current_enrollment(self):
        active = [e for e in self.enrollments if e.status == EnrollmentStatus.ACTIVE]
        return active[0] if active else (self.enrollments[0] if self.enrollments else None)

    def enrollment_for(self, session_id: int):
        return next((e for e in self.enrollments if e.session_id == session_id), None)

    @property
    def age(self) -> int | None:
        if not self.dob:
            return None
        today = date.today()
        return today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Student {self.admission_no} {self.full_name}>"


class Enrollment(TimestampMixin, db.Model):
    __tablename__ = "enrollments"
    __table_args__ = (
        db.UniqueConstraint("student_id", "session_id", name="uq_enrollment_student_session"),
        db.UniqueConstraint("section_id", "roll_no", name="uq_enrollment_section_roll"),
        db.UniqueConstraint("section_id", "student_id", name="uq_enrollment_section_student"),
        db.Index("ix_enrollment_session", "session_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="RESTRICT"), nullable=False
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("academic_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    section_id = db.Column(
        db.Integer, db.ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False
    )
    roll_no = db.Column(db.Integer, nullable=True)
    status = enum_column(EnrollmentStatus, nullable=False, default=EnrollmentStatus.ACTIVE)
    admitted_on = db.Column(db.Date, default=date.today, nullable=True)
    previous_school = db.Column(db.String(200), nullable=True)
    previous_class = db.Column(db.String(40), nullable=True)
    remarks = db.Column(db.String(255), nullable=True)

    student = db.relationship("Student", back_populates="enrollments")
    session = db.relationship("AcademicSession", backref=db.backref("enrollments", lazy="dynamic"))
    section = db.relationship(
        "Section", back_populates="enrollments", foreign_keys=[section_id]
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Enrollment {self.student_id}@{self.section_id}>"


class Guardian(TimestampMixin, db.Model):
    __tablename__ = "guardians"
    __table_args__ = (db.UniqueConstraint("user_id", name="uq_guardian_user"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # A guardian can exist without a portal login (e.g. recorded at admission
    # and invited later). Login is optional, the relationship is not.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    full_name = db.Column(db.String(120), nullable=False)
    occupation = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    alt_phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(160), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User", back_populates="guardian", foreign_keys=[user_id])
    links = db.relationship(
        "GuardianStudentLink", back_populates="guardian", cascade="all, delete-orphan"
    )

    @property
    def verified_students(self):
        return [link.student for link in self.links if link.status == LinkStatus.VERIFIED]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Guardian {self.full_name}>"


class GuardianStudentLink(TimestampMixin, db.Model):
    """Permissions live on the relationship, never on the guardian alone."""

    __tablename__ = "guardian_student_links"
    __table_args__ = (
        db.UniqueConstraint("guardian_id", "student_id", name="uq_guardian_student"),
        db.Index("ix_link_student_status", "student_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    guardian_id = db.Column(
        db.Integer, db.ForeignKey("guardians.id", ondelete="CASCADE"), nullable=False
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    relationship = db.Column(db.String(40), default="Guardian", nullable=False)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)

    can_view_academics = db.Column(db.Boolean, default=True, nullable=False)
    can_view_attendance = db.Column(db.Boolean, default=True, nullable=False)
    can_pay_fees = db.Column(db.Boolean, default=True, nullable=False)
    can_apply_leave = db.Column(db.Boolean, default=True, nullable=False)
    can_view_homework = db.Column(db.Boolean, default=True, nullable=False)
    receive_notifications = db.Column(db.Boolean, default=True, nullable=False)

    status = enum_column(LinkStatus, nullable=False, default=LinkStatus.PENDING)
    verified_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    verified_at = db.Column(db.DateTime, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    guardian = db.relationship("Guardian", back_populates="links")
    student = db.relationship("Student", back_populates="guardian_links")

    @property
    def is_active(self) -> bool:
        return self.status == LinkStatus.VERIFIED

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Link {self.guardian_id}-{self.student_id}>"


class StudentDocument(TimestampMixin, db.Model):
    __tablename__ = "student_documents"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    file_id = db.Column(
        db.Integer, db.ForeignKey("stored_files.id", ondelete="RESTRICT"), nullable=False
    )
    doc_type = enum_column(DocumentType, nullable=False, default=DocumentType.OTHER)
    label = db.Column(db.String(120), nullable=True)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    student = db.relationship("Student", backref=db.backref("documents", lazy="dynamic"))
    file = db.relationship("StoredFile")
