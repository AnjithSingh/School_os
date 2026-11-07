"""Report-card and fee-receipt PDF generation and authorised download."""
from __future__ import annotations

from pathlib import Path

from app.extensions import db
from app.models import StudentFee
from app.models.enums import ExamStatus, PaymentMethod
from app.services import exams as exam_service
from app.services import fees as fee_service
from app.utils.pdf import build_receipt_pdf, build_report_card_pdf
from tests.helpers import login, make_exam, sheet_for


def _computed_exam(demo, *, status=ExamStatus.APPROVED, marks=88):
    exam = make_exam(demo, status=status)
    sheet = sheet_for(exam, demo["section"], demo["subjects"]["maths"].id)
    exam_service.save_marks(
        sheet,
        {demo["rohan"].id: {"status": "PRESENT", "marks": marks}},
        actor_id=demo["teacher_user"].id,
    )
    exam_service.compute_results(exam, actor_id=demo["admin"].id)
    return exam


def test_report_card_pdf_is_a_valid_pdf(app, demo, tmp_path):
    exam = _computed_exam(demo)
    snapshot = exam_service.build_snapshot(exam, demo["rohan"])

    path = Path(build_report_card_pdf(snapshot, "report.pdf"))
    try:
        data = path.read_bytes()
        assert data.startswith(b"%PDF")
        assert len(data) > 1000
    finally:
        path.unlink(missing_ok=True)


def test_generate_report_card_stores_the_pdf(app, demo, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    exam = _computed_exam(demo)

    card = exam_service.generate_report_card(exam, demo["rohan"], actor_id=demo["admin"].id)

    assert card.pdf_file is not None
    stored = Path(card.pdf_file.stored_path)
    assert stored.exists()
    assert stored.read_bytes().startswith(b"%PDF")
    assert card.snapshot_json


def test_draft_report_card_is_not_downloadable_by_a_parent(client, demo, tmp_path):
    app = client.application
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    exam = _computed_exam(demo)
    card = exam_service.generate_report_card(exam, demo["rohan"], actor_id=demo["admin"].id)

    login(client, "parent", "Parent@12345", endpoint="/parent/login")
    assert client.get(f"/parent/report-cards/{card.id}.pdf").status_code == 404


def test_published_report_card_can_be_downloaded_by_parent_and_student(
    client, demo, tmp_path
):
    app = client.application
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    exam = _computed_exam(demo)
    card = exam_service.generate_report_card(exam, demo["rohan"], actor_id=demo["admin"].id)
    exam_service.publish(exam, actor_id=demo["admin"].id)
    db.session.refresh(card)
    assert card.is_published

    login(client, "parent", "Parent@12345", endpoint="/parent/login")
    listing = client.get(f"/parent/children/{demo['rohan'].id}/report-cards")
    assert listing.status_code == 200
    assert b"Download" in listing.data

    response = client.get(f"/parent/report-cards/{card.id}.pdf", follow_redirects=True)
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")

    student_client = app.test_client()
    login(student_client, "student", "Student@12345", endpoint="/student/login")
    own = student_client.get(f"/student/report-cards/{card.id}.pdf", follow_redirects=True)
    assert own.status_code == 200
    assert own.data.startswith(b"%PDF")


def test_receipt_pdf_is_generated_from_a_payment(app, demo, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    fee_service.generate_for_section(
        demo["session"].id, demo["section"].id, actor_id=demo["admin"].id
    )
    fee = StudentFee.query.filter_by(student_id=demo["rohan"].id).one()
    payment = fee_service.record_payment(
        student_fee=fee,
        amount_paise=1_000_000,
        method=PaymentMethod.CASH,
        actor_id=demo["admin"].id,
    )

    context = fee_service.receipt_context(payment)
    path = Path(build_receipt_pdf(context, "receipt.pdf"))
    try:
        assert path.read_bytes().startswith(b"%PDF")
    finally:
        path.unlink(missing_ok=True)
