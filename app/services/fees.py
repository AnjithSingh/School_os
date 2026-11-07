"""Fee structures, student ledgers, payments and receipts."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func

from ..extensions import db
from ..models import (
    Enrollment,
    FeeCategory,
    FeeConcession,
    FeePayment,
    FeeStructure,
    ReceiptCounter,
    StudentFee,
)
from ..models.base import utcnow
from ..models.enums import (
    ConcessionStatus,
    ConcessionType,
    EnrollmentStatus,
    FeeStatus,
    PaymentMethod,
    PaymentStatus,
)
from .audit import record
from ..utils.pdf import amount_in_words


class FeeError(Exception):
    pass


def concession_for(student_id: int, session_id: int, category_id: int, gross_paise: int) -> int:
    rows = FeeConcession.query.filter_by(
        student_id=student_id, session_id=session_id, status=ConcessionStatus.APPROVED
    ).all()
    total = 0
    for row in rows:
        if row.fee_category_id and row.fee_category_id != category_id:
            continue
        if row.concession_type == ConcessionType.PERCENT:
            total += int(gross_paise * min(row.value, 100) / 100)
        else:
            total += row.value
    return min(total, gross_paise)


def generate_for_section(session_id: int, section_id: int, actor_id: int | None = None) -> int:
    section_enrollments = Enrollment.query.filter_by(
        session_id=session_id, section_id=section_id, status=EnrollmentStatus.ACTIVE
    ).all()
    if not section_enrollments:
        return 0

    school_class_id = section_enrollments[0].section.school_class_id
    structures = FeeStructure.query.filter_by(
        session_id=session_id, school_class_id=school_class_id, is_active=True
    ).all()

    created = 0
    for enrollment in section_enrollments:
        for structure in structures:
            existing = StudentFee.query.filter_by(
                student_id=enrollment.student_id, fee_structure_id=structure.id
            ).first()
            if existing:
                continue
            concession = concession_for(
                enrollment.student_id, session_id, structure.fee_category_id, structure.amount_paise
            )
            net = max(structure.amount_paise - concession, 0)
            db.session.add(
                StudentFee(
                    school_id=enrollment.school_id,
                    enrollment_id=enrollment.id,
                    student_id=enrollment.student_id,
                    session_id=session_id,
                    fee_structure_id=structure.id,
                    gross_paise=structure.amount_paise,
                    concession_paise=concession,
                    net_paise=net,
                    paid_paise=0,
                    due_date=structure.due_date,
                    status=FeeStatus.WAIVED if net == 0 else FeeStatus.PENDING,
                )
            )
            created += 1
    if created:
        record("fees.generated", "Section", section_id,
               summary=f"{created} fee records created", actor_id=actor_id)
    db.session.commit()
    return created


def regenerate_concession(student_id: int, session_id: int, actor_id: int | None = None) -> int:
    """Recompute unpaid student fee rows after a concession is approved."""
    updated = 0
    rows = StudentFee.query.filter_by(student_id=student_id, session_id=session_id).all()
    for row in rows:
        if row.paid_paise > 0:
            continue
        concession = concession_for(
            student_id, session_id, row.fee_structure.fee_category_id, row.gross_paise
        )
        row.concession_paise = concession
        row.net_paise = max(row.gross_paise - concession, 0)
        row.status = FeeStatus.WAIVED if row.net_paise == 0 else FeeStatus.PENDING
        updated += 1
    record("fees.recalculated", "Student", student_id, summary=str(updated), actor_id=actor_id)
    db.session.commit()
    return updated


def next_receipt_no(session_id: int, school_id: int) -> str:
    counter = ReceiptCounter.query.filter_by(session_id=session_id).first()
    if counter is None:
        counter = ReceiptCounter(
            school_id=school_id, session_id=session_id, prefix="RCPT", next_no=1
        )
        db.session.add(counter)
        db.session.flush()
    number = f"{counter.prefix}-{counter.next_no:05d}"
    counter.next_no += 1
    return number


def record_payment(
    *,
    student_fee: StudentFee,
    amount_paise: int,
    method: PaymentMethod | str,
    actor_id: int,
    reference: str | None = None,
    notes: str | None = None,
    paid_at: datetime | None = None,
) -> FeePayment:
    if amount_paise <= 0:
        raise FeeError("Enter an amount greater than zero.")
    if amount_paise > student_fee.balance_paise:
        raise FeeError(
            f"Amount exceeds the outstanding balance of {student_fee.balance_paise / 100:.2f}."
        )
    try:
        method = PaymentMethod(method)
    except ValueError:
        raise FeeError("Choose a valid payment method.")

    receipt_no = next_receipt_no(student_fee.session_id, student_fee.school_id)
    payment = FeePayment(
        school_id=student_fee.school_id,
        student_fee_id=student_fee.id,
        student_id=student_fee.student_id,
        session_id=student_fee.session_id,
        receipt_no=receipt_no,
        amount_paise=amount_paise,
        method=method,
        reference=reference,
        paid_at=paid_at or utcnow(),
        collected_by_id=actor_id,
        status=PaymentStatus.SUCCESS,
        notes=notes,
    )
    db.session.add(payment)
    db.session.flush()

    student_fee.paid_paise = min(student_fee.paid_paise + amount_paise, student_fee.net_paise)
    if student_fee.paid_paise >= student_fee.net_paise:
        student_fee.status = FeeStatus.PAID
    elif student_fee.paid_paise > 0:
        student_fee.status = FeeStatus.PARTIAL

    record("fees.payment", "FeePayment", payment.id,
           summary=f"{receipt_no} · {amount_paise}", actor_id=actor_id)
    db.session.commit()
    return payment


def reverse_payment(payment: FeePayment, reason: str, actor_id: int) -> FeePayment:
    if payment.status == PaymentStatus.REVERSED:
        raise FeeError("This payment was already reversed.")
    reversal = FeePayment(
        school_id=payment.school_id,
        student_fee_id=payment.student_fee_id,
        student_id=payment.student_id,
        session_id=payment.session_id,
        receipt_no=f"REV-{payment.receipt_no}",
        amount_paise=payment.amount_paise,
        method=payment.method,
        paid_at=utcnow(),
        collected_by_id=actor_id,
        status=PaymentStatus.REVERSED,
        reversal_of_id=payment.id,
        notes=reason[:255],
    )
    db.session.add(reversal)
    payment.status = PaymentStatus.REVERSED

    if payment.student_fee:
        fee = payment.student_fee
        fee.paid_paise = max(fee.paid_paise - payment.amount_paise, 0)
        fee.status = (
            FeeStatus.PAID if fee.paid_paise >= fee.net_paise and fee.net_paise
            else FeeStatus.PARTIAL if fee.paid_paise > 0
            else FeeStatus.PENDING
        )
    record("fees.reversed", "FeePayment", payment.id, summary=reason, actor_id=actor_id)
    db.session.commit()
    return reversal


def student_ledger(student_id: int, session_id: int) -> dict:
    rows = (
        StudentFee.query.filter_by(student_id=student_id, session_id=session_id)
        .join(StudentFee.fee_structure)
        .order_by(FeeStructure.due_date, StudentFee.id)
        .all()
    )
    payments = (
        FeePayment.query.filter_by(student_id=student_id, session_id=session_id)
        .order_by(FeePayment.paid_at.desc())
        .all()
    )
    total_net = sum(r.net_paise for r in rows)
    total_paid = sum(r.paid_paise for r in rows)
    return {
        "rows": rows,
        "payments": payments,
        "total_net": total_net,
        "total_paid": total_paid,
        "balance": max(total_net - total_paid, 0),
        "overdue": sum(
            r.balance_paise
            for r in rows
            if r.due_date and r.due_date < date.today() and r.balance_paise > 0
        ),
    }


def receipt_context(payment: FeePayment) -> dict:
    from .settings import get_school

    school = get_school()
    fee = payment.student_fee
    enrollment = fee.enrollment if fee else None
    items = []
    if fee:
        items.append(
            {
                "label": f"{fee.fee_structure.category.name} · installment {fee.fee_structure.installment_no}",
                "amount_paise": fee.gross_paise,
            }
        )
        if fee.concession_paise:
            items.append(
                {"label": "Concession", "amount_paise": -fee.concession_paise}
            )
        items.append({"label": "Balance after payment", "amount_paise": fee.balance_paise})
    return {
        "school": {
            "name": school.name,
            "address": school.address,
            "phone": school.phone,
            "email": school.email,
            "accent": school.secondary_color,
        },
        "receipt_no": payment.receipt_no,
        "paid_at": payment.paid_at.strftime("%d %b %Y, %I:%M %p"),
        "student": payment.student.full_name,
        "class_section": enrollment.section.label if enrollment else "—",
        "amount_paise": payment.amount_paise,
        "method": payment.method.value.replace("_", " ").title(),
        "items": items,
        "amount_words": amount_in_words(payment.amount_paise),
    }


def collection_summary(session_id: int) -> dict:
    collected = (
        db.session.query(func.coalesce(func.sum(FeePayment.amount_paise), 0))
        .filter(
            FeePayment.session_id == session_id,
            FeePayment.status == PaymentStatus.SUCCESS,
        )
        .scalar()
    )
    reversed_total = (
        db.session.query(func.coalesce(func.sum(FeePayment.amount_paise), 0))
        .filter(
            FeePayment.session_id == session_id,
            FeePayment.status == PaymentStatus.REVERSED,
        )
        .scalar()
    )
    billed = (
        db.session.query(func.coalesce(func.sum(StudentFee.net_paise), 0))
        .filter(StudentFee.session_id == session_id)
        .scalar()
    )
    paid_rows = (
        db.session.query(func.coalesce(func.sum(StudentFee.paid_paise), 0))
        .filter(StudentFee.session_id == session_id)
        .scalar()
    )
    return {
        "collected": collected - reversed_total,
        "billed": billed,
        "paid": paid_rows,
        "outstanding": max(billed - paid_rows, 0),
        "collection_rate": round(paid_rows / billed * 100, 1) if billed else 0,
    }


def overdue_fees(session_id: int, limit: int = 10):
    return (
        StudentFee.query.filter(
            StudentFee.session_id == session_id,
            StudentFee.due_date < date.today(),
            StudentFee.status.in_([FeeStatus.PENDING, FeeStatus.PARTIAL]),
        )
        .order_by(StudentFee.due_date)
        .limit(limit)
        .all()
    )


def categories(session_id: int):
    return (
        FeeCategory.query.filter_by(session_id=session_id, is_active=True)
        .order_by(FeeCategory.name)
        .all()
    )
