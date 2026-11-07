"""Fees, concessions and payments. All money is stored as integer paise."""
from __future__ import annotations

from ..extensions import db
from .base import TenantMixin, TimestampMixin, enum_column
from .enums import (
    ConcessionStatus,
    ConcessionType,
    FeeFrequency,
    FeeStatus,
    PaymentMethod,
    PaymentStatus,
)


class FeeCategory(TimestampMixin, db.Model):
    __tablename__ = "fee_categories"
    __table_args__ = (db.UniqueConstraint("session_id", "code", name="uq_fee_category_code"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("academic_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    code = db.Column(db.String(30), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    frequency = enum_column(FeeFrequency, nullable=False, default=FeeFrequency.ANNUAL)
    is_optional = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)

    session = db.relationship("AcademicSession", backref=db.backref("fee_categories", lazy="dynamic"))


class FeeStructure(TimestampMixin, db.Model):
    __tablename__ = "fee_structures"
    __table_args__ = (
        db.UniqueConstraint(
            "session_id",
            "school_class_id",
            "fee_category_id",
            "installment_no",
            name="uq_fee_structure_class_category_installment",
        ),
        db.CheckConstraint("amount_paise >= 0", name="fee_amount_positive"),
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
    fee_category_id = db.Column(
        db.Integer, db.ForeignKey("fee_categories.id", ondelete="RESTRICT"), nullable=False
    )
    installment_no = db.Column(db.Integer, default=1, nullable=False)
    amount_paise = db.Column(db.Integer, default=0, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    category = db.relationship("FeeCategory")
    school_class = db.relationship("SchoolClass")


class FeeConcession(TimestampMixin, db.Model):
    __tablename__ = "fee_concessions"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("academic_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    fee_category_id = db.Column(
        db.Integer, db.ForeignKey("fee_categories.id", ondelete="SET NULL")
    )
    concession_type = enum_column(ConcessionType, nullable=False, default=ConcessionType.PERCENT)
    value = db.Column(db.Integer, default=0, nullable=False)  # percent or paise
    reason = db.Column(db.String(255), nullable=True)
    status = enum_column(ConcessionStatus, nullable=False, default=ConcessionStatus.PENDING)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    approved_at = db.Column(db.DateTime, nullable=True)
    valid_from = db.Column(db.Date, nullable=True)
    valid_to = db.Column(db.Date, nullable=True)

    student = db.relationship("Student")
    category = db.relationship("FeeCategory")
    approved_by = db.relationship("User")


class StudentFee(TimestampMixin, db.Model):
    __tablename__ = "student_fees"
    __table_args__ = (
        db.UniqueConstraint("student_id", "fee_structure_id", name="uq_student_fee_structure"),
        db.Index("ix_student_fee_status", "session_id", "status"),
        db.CheckConstraint("net_paise >= 0", name="net_non_negative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    enrollment_id = db.Column(
        db.Integer, db.ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=False
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="RESTRICT"), nullable=False
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("academic_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    fee_structure_id = db.Column(
        db.Integer, db.ForeignKey("fee_structures.id", ondelete="RESTRICT"), nullable=False
    )
    gross_paise = db.Column(db.Integer, default=0, nullable=False)
    concession_paise = db.Column(db.Integer, default=0, nullable=False)
    net_paise = db.Column(db.Integer, default=0, nullable=False)
    paid_paise = db.Column(db.Integer, default=0, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    status = enum_column(FeeStatus, nullable=False, default=FeeStatus.PENDING)

    student = db.relationship("Student", backref=db.backref("fees", lazy="dynamic"))
    enrollment = db.relationship("Enrollment")
    fee_structure = db.relationship("FeeStructure")
    payments = db.relationship("FeePayment", back_populates="student_fee", lazy="selectin")

    @property
    def balance_paise(self) -> int:
        return max(self.net_paise - self.paid_paise, 0)

    @property
    def is_overdue(self) -> bool:
        from datetime import date

        return self.status in (FeeStatus.PENDING, FeeStatus.PARTIAL) and bool(
            self.due_date and self.due_date < date.today()
        )


class FeePayment(TimestampMixin, db.Model):
    """Append-only ledger. Reversals create a new row; nothing is deleted."""

    __tablename__ = "fee_payments"
    __table_args__ = (
        db.UniqueConstraint("session_id", "receipt_no", name="uq_payment_receipt_no"),
        db.Index("ix_payment_student", "student_id", "status"),
        db.Index("ix_payment_paid_at", "paid_at"),
        db.CheckConstraint("amount_paise > 0", name="payment_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_fee_id = db.Column(
        db.Integer, db.ForeignKey("student_fees.id", ondelete="RESTRICT"), nullable=True
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="RESTRICT"), nullable=False
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("academic_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    receipt_no = db.Column(db.String(40), nullable=False)
    amount_paise = db.Column(db.Integer, nullable=False)
    method = enum_column(PaymentMethod, nullable=False, default=PaymentMethod.CASH)
    reference = db.Column(db.String(120), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=False)
    collected_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    status = enum_column(PaymentStatus, nullable=False, default=PaymentStatus.SUCCESS)
    reversal_of_id = db.Column(db.Integer, db.ForeignKey("fee_payments.id", ondelete="SET NULL"))
    notes = db.Column(db.String(255), nullable=True)

    student_fee = db.relationship("StudentFee", back_populates="payments")
    student = db.relationship("Student")
    collected_by = db.relationship("User", foreign_keys=[collected_by_id])
    reversal_of = db.relationship("FeePayment", remote_side=[id], foreign_keys=[reversal_of_id])


class ReceiptCounter(TimestampMixin, db.Model):
    __tablename__ = "receipt_counters"
    __table_args__ = (db.UniqueConstraint("session_id", name="uq_receipt_counter_session"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("academic_sessions.id", ondelete="CASCADE"), nullable=False
    )
    prefix = db.Column(db.String(20), default="RCPT", nullable=False)
    next_no = db.Column(db.Integer, default=1, nullable=False)
