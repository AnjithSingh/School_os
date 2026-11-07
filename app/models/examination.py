"""Examination, marks, grading and report-card models."""
from __future__ import annotations

from ..extensions import db
from .base import TenantMixin, TimestampMixin, enum_column
from .enums import ExamStatus, MarkStatus, ReportCardStatus, ResultStatus, SheetStatus


class ExamType(TimestampMixin, db.Model):
    """FA1..Final are seeded data, never hardcoded strings in the code."""

    __tablename__ = "exam_types"
    __table_args__ = (db.UniqueConstraint("school_id", "code", name="uq_exam_type_code"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    sequence = db.Column(db.Integer, default=0, nullable=False)
    default_weight = db.Column(db.Integer, default=0, nullable=False)
    is_terminal = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ExamType {self.code}>"


class Examination(TimestampMixin, db.Model):
    __tablename__ = "examinations"
    __table_args__ = (
        db.UniqueConstraint(
            "session_id", "exam_type_id", "name", name="uq_exam_session_type_name"
        ),
        db.Index("ix_exam_status", "school_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("academic_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    exam_type_id = db.Column(
        db.Integer, db.ForeignKey("exam_types.id", ondelete="RESTRICT"), nullable=False
    )
    name = db.Column(db.String(120), nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    result_date = db.Column(db.Date, nullable=True)
    status = enum_column(ExamStatus, nullable=False, default=ExamStatus.DRAFT)
    instructions = db.Column(db.Text, nullable=True)
    grading_scale_id = db.Column(
        db.Integer, db.ForeignKey("grade_scales.id", ondelete="SET NULL")
    )
    pass_policy_json = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    published_at = db.Column(db.DateTime, nullable=True)

    exam_type = db.relationship("ExamType")
    session = db.relationship("AcademicSession", backref=db.backref("examinations", lazy="dynamic"))
    grading_scale = db.relationship("GradeScale", foreign_keys=[grading_scale_id])
    subjects = db.relationship(
        "ExaminationSubject", back_populates="examination", cascade="all, delete-orphan"
    )
    classes = db.relationship(
        "ExaminationClass", back_populates="examination", cascade="all, delete-orphan"
    )

    @property
    def label(self) -> str:
        return f"{self.exam_type.name} — {self.name}" if self.exam_type else self.name

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Examination {self.name}>"


class ExaminationClass(TimestampMixin, db.Model):
    __tablename__ = "examination_classes"
    __table_args__ = (
        db.UniqueConstraint(
            "examination_id", "school_class_id", "section_id", name="uq_exam_class_section"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False
    )
    examination_id = db.Column(
        db.Integer, db.ForeignKey("examinations.id", ondelete="CASCADE"), nullable=False
    )
    school_class_id = db.Column(
        db.Integer, db.ForeignKey("school_classes.id", ondelete="RESTRICT"), nullable=False
    )
    section_id = db.Column(db.Integer, db.ForeignKey("sections.id", ondelete="CASCADE"))

    examination = db.relationship("Examination", back_populates="classes")
    school_class = db.relationship("SchoolClass")
    section = db.relationship("Section")


class ExaminationSubject(TimestampMixin, db.Model):
    __tablename__ = "examination_subjects"
    __table_args__ = (
        db.UniqueConstraint(
            "examination_id", "school_class_id", "subject_id", name="uq_exam_class_subject"
        ),
        db.CheckConstraint("pass_marks <= max_marks", name="pass_within_max"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False
    )
    examination_id = db.Column(
        db.Integer, db.ForeignKey("examinations.id", ondelete="CASCADE"), nullable=False
    )
    school_class_id = db.Column(
        db.Integer, db.ForeignKey("school_classes.id", ondelete="RESTRICT"), nullable=False
    )
    subject_id = db.Column(
        db.Integer, db.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    exam_date = db.Column(db.Date, nullable=True)
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    room = db.Column(db.String(40), nullable=True)
    max_marks = db.Column(db.Integer, default=100, nullable=False)
    pass_marks = db.Column(db.Integer, default=33, nullable=False)
    weight = db.Column(db.Integer, default=100, nullable=False)
    is_optional = db.Column(db.Boolean, default=False, nullable=False)

    examination = db.relationship("Examination", back_populates="subjects")
    school_class = db.relationship("SchoolClass")
    subject = db.relationship("Subject")
    sheets = db.relationship(
        "MarksEntrySheet", back_populates="exam_subject", cascade="all, delete-orphan"
    )


class MarksEntrySheet(TimestampMixin, db.Model):
    """One sheet per examination subject per section — the unit teachers submit."""

    __tablename__ = "marks_entry_sheets"
    __table_args__ = (
        db.UniqueConstraint(
            "examination_subject_id", "section_id", name="uq_sheet_subject_section"
        ),
        db.Index("ix_sheet_teacher_status", "teacher_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    examination_subject_id = db.Column(
        db.Integer, db.ForeignKey("examination_subjects.id", ondelete="CASCADE"), nullable=False
    )
    section_id = db.Column(
        db.Integer, db.ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False
    )
    teacher_id = db.Column(
        db.Integer, db.ForeignKey("staff_profiles.id", ondelete="RESTRICT"), nullable=True
    )
    status = enum_column(SheetStatus, nullable=False, default=SheetStatus.DRAFT)
    submitted_at = db.Column(db.DateTime, nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    approved_at = db.Column(db.DateTime, nullable=True)
    remarks = db.Column(db.String(255), nullable=True)

    exam_subject = db.relationship("ExaminationSubject", back_populates="sheets")
    section = db.relationship("Section")
    teacher = db.relationship("StaffProfile")
    approved_by = db.relationship("User", foreign_keys=[approved_by_id])
    records = db.relationship(
        "MarksRecord", back_populates="sheet", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def entered_count(self) -> int:
        return len([r for r in self.records if r.marks_obtained is not None or r.status != MarkStatus.PRESENT])


class MarksRecord(TimestampMixin, db.Model):
    __tablename__ = "marks_records"
    __table_args__ = (
        db.UniqueConstraint("sheet_id", "student_id", name="uq_marks_sheet_student"),
        db.Index("ix_marks_student", "student_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sheet_id = db.Column(
        db.Integer, db.ForeignKey("marks_entry_sheets.id", ondelete="CASCADE"), nullable=False
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="RESTRICT"), nullable=False
    )
    enrollment_id = db.Column(
        db.Integer, db.ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=True
    )
    marks_obtained = db.Column(db.Integer, nullable=True)
    status = enum_column(MarkStatus, nullable=False, default=MarkStatus.PRESENT)
    remarks = db.Column(db.String(255), nullable=True)
    is_modified = db.Column(db.Boolean, default=False, nullable=False)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    sheet = db.relationship("MarksEntrySheet", back_populates="records")
    student = db.relationship("Student")
    enrollment = db.relationship("Enrollment")

    @property
    def counted(self) -> bool:
        return self.status != MarkStatus.EXEMPT


class MarksAudit(db.Model):
    __tablename__ = "marks_audits"
    __table_args__ = (db.Index("ix_marks_audit_record", "marks_record_id"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False
    )
    marks_record_id = db.Column(
        db.Integer, db.ForeignKey("marks_records.id", ondelete="CASCADE"), nullable=False
    )
    old_marks = db.Column(db.Integer, nullable=True)
    new_marks = db.Column(db.Integer, nullable=True)
    old_status = db.Column(db.String(20), nullable=True)
    new_status = db.Column(db.String(20), nullable=True)
    reason = db.Column(db.String(255), nullable=False)
    changed_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, nullable=False)

    changed_by = db.relationship("User")


class GradeScale(TimestampMixin, db.Model):
    __tablename__ = "grade_scales"
    __table_args__ = (
        db.UniqueConstraint("school_id", "name", name="uq_grade_scale_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name = db.Column(db.String(80), nullable=False)
    is_default = db.Column(db.Boolean, default=False, nullable=False)

    rules = db.relationship(
        "GradeRule", back_populates="scale", cascade="all, delete-orphan",
        order_by="GradeRule.min_percent.desc()",
    )

    def rule_for(self, percentage: float):
        """Return the grade band that applies to ``percentage``.

        Boundaries are compared inclusively, but schools configure integer
        bands (for example 0-32, 33-40). A fractional score such as 32.9 must
        still receive a grade, so a score that clears a band's lower bound
        falls into that band even when it sits inside the configured gap.
        Rules are ordered highest-first, therefore the first lower-bound match
        is the closest band at or below the score.
        """
        rules = list(self.rules)
        for rule in rules:
            if rule.min_percent <= percentage <= rule.max_percent:
                return rule
        for rule in rules:
            if percentage >= rule.min_percent:
                return rule
        return None


class GradeRule(db.Model):
    __tablename__ = "grade_rules"
    __table_args__ = (
        db.UniqueConstraint("grade_scale_id", "grade", name="uq_grade_rule_grade"),
        db.CheckConstraint("min_percent <= max_percent", name="grade_range"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False
    )
    grade_scale_id = db.Column(
        db.Integer, db.ForeignKey("grade_scales.id", ondelete="CASCADE"), nullable=False
    )
    grade = db.Column(db.String(8), nullable=False)
    min_percent = db.Column(db.Float, nullable=False)
    max_percent = db.Column(db.Float, nullable=False)
    grade_point = db.Column(db.Float, nullable=True)
    description = db.Column(db.String(120), nullable=True)
    sort_order = db.Column(db.Integer, default=0, nullable=False)

    scale = db.relationship("GradeScale", back_populates="rules")


class ResultSummary(TimestampMixin, db.Model):
    __tablename__ = "result_summaries"
    __table_args__ = (
        db.UniqueConstraint("examination_id", "student_id", name="uq_result_exam_student"),
        db.Index("ix_result_status", "examination_id", "result_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    examination_id = db.Column(
        db.Integer, db.ForeignKey("examinations.id", ondelete="CASCADE"), nullable=False
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="RESTRICT"), nullable=False
    )
    enrollment_id = db.Column(
        db.Integer, db.ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=True
    )
    section_id = db.Column(db.Integer, db.ForeignKey("sections.id", ondelete="RESTRICT"))
    total_max = db.Column(db.Integer, default=0, nullable=False)
    total_obtained = db.Column(db.Integer, default=0, nullable=False)
    percentage = db.Column(db.Float, default=0.0, nullable=False)
    grade = db.Column(db.String(8), nullable=True)
    grade_point = db.Column(db.Float, nullable=True)
    result_status = enum_column(ResultStatus, nullable=False, default=ResultStatus.PASS)
    subjects_failed = db.Column(db.Integer, default=0, nullable=False)
    computed_version = db.Column(db.Integer, default=1, nullable=False)
    computed_at = db.Column(db.DateTime, nullable=True)

    examination = db.relationship("Examination", backref=db.backref("results", lazy="dynamic"))
    student = db.relationship("Student")
    section = db.relationship("Section")

    @property
    def tone(self) -> str:
        return self.result_status.tone


class ExamRemark(TimestampMixin, db.Model):
    __tablename__ = "exam_remarks"
    __table_args__ = (
        db.UniqueConstraint("examination_id", "student_id", name="uq_remark_exam_student"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False
    )
    examination_id = db.Column(
        db.Integer, db.ForeignKey("examinations.id", ondelete="CASCADE"), nullable=False
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    teacher_remark = db.Column(db.String(400), nullable=True)
    principal_remark = db.Column(db.String(400), nullable=True)
    written_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    examination = db.relationship("Examination")
    student = db.relationship("Student")


class ReportCard(TimestampMixin, db.Model):
    """Immutable snapshot so later grading changes never rewrite history."""

    __tablename__ = "report_cards"
    __table_args__ = (
        db.UniqueConstraint(
            "examination_id", "student_id", "revision", name="uq_report_card_revision"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    result_summary_id = db.Column(
        db.Integer, db.ForeignKey("result_summaries.id", ondelete="CASCADE"), nullable=False
    )
    examination_id = db.Column(
        db.Integer, db.ForeignKey("examinations.id", ondelete="CASCADE"), nullable=False
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="RESTRICT"), nullable=False
    )
    template_version = db.Column(db.String(20), default="v1", nullable=False)
    snapshot_json = db.Column(db.Text, nullable=False)
    pdf_file_id = db.Column(db.Integer, db.ForeignKey("stored_files.id", ondelete="SET NULL"))
    status = enum_column(ReportCardStatus, nullable=False, default=ReportCardStatus.DRAFT)
    revision = db.Column(db.Integer, default=1, nullable=False)
    generated_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    published_at = db.Column(db.DateTime, nullable=True)

    examination = db.relationship("Examination")
    student = db.relationship("Student")
    pdf_file = db.relationship("StoredFile")

    @property
    def is_published(self) -> bool:
        return self.status != ReportCardStatus.DRAFT
