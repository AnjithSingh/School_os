"""Fee generation, concessions, payments and ledger logic."""
from __future__ import annotations

from datetime import date

import pytest

from app.extensions import db
from app.models import FeeConcession, FeePayment, StudentFee
from app.models.enums import ConcessionStatus, ConcessionType, FeeStatus, PaymentMethod, PaymentStatus
from app.services import fees as fee_service
from app.utils.money import from_paise


def test_generate_for_section_creates_one_row_per_structure(demo):
    created = fee_service.generate_for_section(
        demo["session"].id, demo["section"].id, actor_id=demo["admin"].id
    )
    assert created == 2  # rohan and meera
    assert StudentFee.query.count() == 2


def test_fee_amounts_are_stored_as_integer_paise(demo):
    fee_service.generate_for_section(demo["session"].id, demo["section"].id, actor_id=demo["admin"].id)
    fee = StudentFee.query.filter_by(student_id=demo["rohan"].id).one()
    assert fee.gross_paise == 5_000_000
    assert float(from_paise(fee.gross_paise)) == 50000.0


def test_approved_concession_reduces_net(demo):
    fee_service.generate_for_section(demo["session"].id, demo["section"].id, actor_id=demo["admin"].id)
    db.session.add(
        FeeConcession(
            school_id=demo["school"].id,
            student_id=demo["rohan"].id,
            session_id=demo["session"].id,
            fee_category_id=demo["fee_category"].id,
            concession_type=ConcessionType.PERCENT,
            value=10,
            status=ConcessionStatus.APPROVED,
        )
    )
    db.session.commit()

    fee_service.regenerate_concession(demo["rohan"].id, demo["session"].id, actor_id=demo["admin"].id)
    fee = StudentFee.query.filter_by(student_id=demo["rohan"].id).one()
    assert fee.concession_paise == 500_000
    assert fee.net_paise == 4_500_000


def test_category_specific_concession_is_applied(demo):
    fee_service.generate_for_section(demo["session"].id, demo["section"].id, actor_id=demo["admin"].id)
    concession = fee_service.concession_for(
        demo["rohan"].id, demo["session"].id, demo["fee_category"].id, 5_000_000
    )
    assert concession == 0

    db.session.add(
        FeeConcession(
            school_id=demo["school"].id,
            student_id=demo["rohan"].id,
            session_id=demo["session"].id,
            fee_category_id=demo["fee_category"].id,
            concession_type=ConcessionType.AMOUNT,
            value=250_000,
            status=ConcessionStatus.APPROVED,
        )
    )
    db.session.commit()
    assert fee_service.concession_for(demo["rohan"].id, demo["session"].id, demo["fee_category"].id, 5_000_000) == 250_000


def test_record_payment_updates_balance_and_receipt(demo):
    fee_service.generate_for_section(demo["session"].id, demo["section"].id, actor_id=demo["admin"].id)
    fee = StudentFee.query.filter_by(student_id=demo["rohan"].id).one()

    payment = fee_service.record_payment(
        student_fee=fee,
        amount_paise=2_000_000,
        method=PaymentMethod.CASH,
        actor_id=demo["admin"].id,
    )

    assert payment.receipt_no.startswith("RCPT-")
    assert payment.status == PaymentStatus.SUCCESS
    db.session.refresh(fee)
    assert fee.paid_paise == 2_000_000
    assert fee.balance_paise == 3_000_000
    assert fee.status == FeeStatus.PARTIAL


def test_payment_cannot_exceed_balance(demo):
    fee_service.generate_for_section(demo["session"].id, demo["section"].id, actor_id=demo["admin"].id)
    fee = StudentFee.query.filter_by(student_id=demo["rohan"].id).one()

    with pytest.raises(fee_service.FeeError):
        fee_service.record_payment(
            student_fee=fee,
            amount_paise=6_000_000,
            method=PaymentMethod.CASH,
            actor_id=demo["admin"].id,
        )


def test_payment_must_be_positive(demo):
    fee_service.generate_for_section(demo["session"].id, demo["section"].id, actor_id=demo["admin"].id)
    fee = StudentFee.query.filter_by(student_id=demo["rohan"].id).one()

    with pytest.raises(fee_service.FeeError):
        fee_service.record_payment(
            student_fee=fee,
            amount_paise=0,
            method=PaymentMethod.CASH,
            actor_id=demo["admin"].id,
        )


def test_full_payment_marks_fee_paid(demo):
    fee_service.generate_for_section(demo["session"].id, demo["section"].id, actor_id=demo["admin"].id)
    fee = StudentFee.query.filter_by(student_id=demo["rohan"].id).one()

    fee_service.record_payment(
        student_fee=fee,
        amount_paise=5_000_000,
        method=PaymentMethod.BANK_TRANSFER,
        actor_id=demo["admin"].id,
    )
    db.session.refresh(fee)
    assert fee.status == FeeStatus.PAID
    assert fee.balance_paise == 0


def test_reverse_payment_creates_a_reversal_row_and_restores_balance(demo):
    fee_service.generate_for_section(demo["session"].id, demo["section"].id, actor_id=demo["admin"].id)
    fee = StudentFee.query.filter_by(student_id=demo["rohan"].id).one()
    payment = fee_service.record_payment(
        student_fee=fee,
        amount_paise=1_000_000,
        method=PaymentMethod.UPI_OFFLINE,
        actor_id=demo["admin"].id,
    )

    reversal = fee_service.reverse_payment(payment, reason="Duplicate", actor_id=demo["admin"].id)

    assert reversal.status == PaymentStatus.REVERSED
    assert reversal.reversal_of_id == payment.id
    assert reversal.receipt_no.startswith("REV-")
    assert FeePayment.query.count() == 2
    db.session.refresh(payment)
    db.session.refresh(fee)
    assert payment.status == PaymentStatus.REVERSED
    assert fee.paid_paise == 0
    assert fee.status == FeeStatus.PENDING


def test_student_ledger_totals_are_correct(demo):
    fee_service.generate_for_section(demo["session"].id, demo["section"].id, actor_id=demo["admin"].id)
    fee = StudentFee.query.filter_by(student_id=demo["rohan"].id).one()
    fee_service.record_payment(
        student_fee=fee,
        amount_paise=1_500_000,
        method=PaymentMethod.CASH,
        actor_id=demo["admin"].id,
    )

    ledger = fee_service.student_ledger(demo["rohan"].id, demo["session"].id)
    assert ledger["total_net"] == 5_000_000
    assert ledger["total_paid"] == 1_500_000
    assert ledger["balance"] == 3_500_000
    assert len(ledger["rows"]) == 1
    assert len(ledger["payments"]) == 1


def test_waived_fees_are_marked_waived_when_net_is_zero(demo):
    fee_service.generate_for_section(demo["session"].id, demo["section"].id, actor_id=demo["admin"].id)
    fee = StudentFee.query.filter_by(student_id=demo["rohan"].id).one()
    fee.net_paise = 0
    fee.concession_paise = fee.gross_paise
    fee.status = FeeStatus.WAIVED
    db.session.commit()

    assert fee.balance_paise == 0
