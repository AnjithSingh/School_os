"""Marks entry, result computation, grading and report-card snapshots."""
from __future__ import annotations

import json

import pytest

from app.extensions import db
from app.models import ReportCard, ResultSummary
from app.models.enums import ExamStatus, ReportCardStatus
from app.services import exams as exam_service
from tests.helpers import make_exam, sheet_for


@pytest.mark.parametrize(
    ("percentage", "grade", "point"),
    [
        (100, "A1", 10.0),
        (91, "A1", 10.0),
        (90, "A2", 9.0),
        (81, "A2", 9.0),
        (33, "D", 4.0),
        (32.9, "E", 0.0),
        (0, "E", 0.0),
    ],
)
def test_grade_scale_boundaries(demo, percentage, grade, point):
    assert exam_service.grade_for(percentage, demo["grade_scale"]) == (grade, point)


def test_grade_for_without_a_scale_returns_none():
    assert exam_service.grade_for(90, None) == (None, None)


def _marks(exam, demo, subject="maths"):
    return sheet_for(exam, demo["section"], demo["subjects"][subject].id)


def test_save_marks_and_submit_sheet(demo):
    exam = make_exam(demo)
    sheet = _marks(exam, demo)

    result = exam_service.save_marks(
        sheet,
        {
            demo["rohan"].id: {"status": "PRESENT", "marks": 87, "remarks": "Good"},
            demo["meera"].id: {"status": "ABSENT"},
        },
        actor_id=demo["teacher_user"].id,
        submit=True,
    )

    assert result == {"changed": 2, "submitted": True}
    assert sheet.status.value == "SUBMITTED"
    record = next(r for r in sheet.records if r.student_id == demo["rohan"].id)
    assert record.marks_obtained == 87
    absent = next(r for r in sheet.records if r.student_id == demo["meera"].id)
    assert absent.marks_obtained is None
    assert absent.status.value == "ABSENT"


def test_marks_above_maximum_are_rejected(demo):
    exam = make_exam(demo)
    sheet = _marks(exam, demo)

    with pytest.raises(exam_service.MarksError):
        exam_service.save_marks(
            sheet,
            {demo["rohan"].id: {"status": "PRESENT", "marks": 101}},
            actor_id=demo["teacher_user"].id,
        )


def test_present_student_requires_marks(demo):
    exam = make_exam(demo)
    sheet = _marks(exam, demo)

    with pytest.raises(exam_service.MarksError):
        exam_service.save_marks(
            sheet,
            {demo["rohan"].id: {"status": "PRESENT", "marks": ""}},
            actor_id=demo["teacher_user"].id,
        )


def test_approved_sheet_cannot_be_edited(demo):
    exam = make_exam(demo)
    sheet = _marks(exam, demo)
    exam_service.save_marks(
        sheet,
        {demo["rohan"].id: {"status": "PRESENT", "marks": 75}},
        actor_id=demo["teacher_user"].id,
        submit=True,
    )
    exam_service.approve_sheet(sheet, actor_id=demo["admin"].id)

    with pytest.raises(exam_service.MarksError):
        exam_service.save_marks(
            sheet,
            {demo["rohan"].id: {"status": "PRESENT", "marks": 80}},
            actor_id=demo["teacher_user"].id,
        )


def test_marks_correction_is_audited(demo):
    from app.models import MarksAudit

    exam = make_exam(demo)
    sheet = _marks(exam, demo)
    exam_service.save_marks(
        sheet,
        {demo["rohan"].id: {"status": "PRESENT", "marks": 70}},
        actor_id=demo["teacher_user"].id,
    )
    exam_service.save_marks(
        sheet,
        {demo["rohan"].id: {"status": "PRESENT", "marks": 72}},
        actor_id=demo["teacher_user"].id,
        reason="Addition error corrected",
    )

    audit = MarksAudit.query.one()
    assert audit.old_marks == 70
    assert audit.new_marks == 72
    assert audit.reason == "Addition error corrected"


def test_compute_results_for_the_section(demo):
    exam = make_exam(demo, subjects=("maths", "science"))
    exam_service.save_marks(
        _marks(exam, demo, "maths"),
        {
            demo["rohan"].id: {"status": "PRESENT", "marks": 90},
            demo["meera"].id: {"status": "PRESENT", "marks": 20},
        },
        actor_id=demo["teacher_user"].id,
        submit=True,
    )
    exam_service.save_marks(
        _marks(exam, demo, "science"),
        {
            demo["rohan"].id: {"status": "PRESENT", "marks": 80},
            demo["meera"].id: {"status": "PRESENT", "marks": 40},
        },
        actor_id=demo["teacher_user"].id,
        submit=True,
    )

    result = exam_service.compute_results(exam, actor_id=demo["admin"].id)
    assert result["computed"] == 2

    rohan = ResultSummary.query.filter_by(
        examination_id=exam.id, student_id=demo["rohan"].id
    ).one()
    assert (rohan.total_obtained, rohan.total_max) == (170, 200)
    assert rohan.percentage == 85.0
    assert rohan.grade == "A2"
    assert rohan.result_status.value == "PASS"
    assert rohan.subjects_failed == 0

    meera = ResultSummary.query.filter_by(
        examination_id=exam.id, student_id=demo["meera"].id
    ).one()
    assert meera.percentage == 30.0
    assert meera.result_status.value == "FAIL"
    assert meera.subjects_failed == 1


def test_absent_student_scores_zero_and_fails(demo):
    exam = make_exam(demo)
    exam_service.save_marks(
        _marks(exam, demo),
        {demo["rohan"].id: {"status": "ABSENT"}},
        actor_id=demo["teacher_user"].id,
    )
    exam_service.compute_results(exam, actor_id=demo["admin"].id)

    summary = ResultSummary.query.filter_by(
        examination_id=exam.id, student_id=demo["rohan"].id
    ).one()
    assert summary.total_obtained == 0
    assert summary.result_status.value == "FAIL"


def test_report_cards_are_immutable_revisions(demo):
    exam = make_exam(demo, status=ExamStatus.APPROVED)
    sheet = _marks(exam, demo)
    exam_service.save_marks(
        sheet,
        {demo["rohan"].id: {"status": "PRESENT", "marks": 88}},
        actor_id=demo["teacher_user"].id,
    )
    exam_service.compute_results(exam, actor_id=demo["admin"].id)

    first = exam_service.generate_report_card(exam, demo["rohan"], actor_id=demo["admin"].id)
    first_snapshot = json.loads(first.snapshot_json)
    assert first.revision == 1
    assert first.status == ReportCardStatus.DRAFT
    assert first_snapshot["totals"]["percentage"] == 88.0

    exam_service.save_marks(
        sheet,
        {demo["rohan"].id: {"status": "PRESENT", "marks": 70}},
        actor_id=demo["teacher_user"].id,
        reason="Re-evaluation",
    )
    exam_service.compute_results(exam, actor_id=demo["admin"].id)
    second = exam_service.generate_report_card(exam, demo["rohan"], actor_id=demo["admin"].id)

    assert second.revision == 2
    # The earlier card still shows the original marks.
    assert json.loads(first.snapshot_json)["totals"]["percentage"] == 88.0
    assert json.loads(second.snapshot_json)["totals"]["percentage"] == 70.0
    assert ReportCard.query.filter_by(student_id=demo["rohan"].id).count() == 2


def test_publish_marks_results_and_cards_visible(demo):
    exam = make_exam(demo, status=ExamStatus.APPROVED)
    exam_service.save_marks(
        _marks(exam, demo),
        {demo["rohan"].id: {"status": "PRESENT", "marks": 88}},
        actor_id=demo["teacher_user"].id,
    )
    exam_service.compute_results(exam, actor_id=demo["admin"].id)
    card = exam_service.generate_report_card(exam, demo["rohan"], actor_id=demo["admin"].id)

    exam_service.publish(exam, actor_id=demo["admin"].id)

    db.session.refresh(exam)
    db.session.refresh(card)
    assert exam.status == ExamStatus.PUBLISHED
    assert exam.published_at is not None
    assert card.status == ReportCardStatus.PUBLISHED
    assert card.is_published is True


def test_subject_breakdown_matches_entered_marks(demo):
    exam = make_exam(demo)
    exam_service.save_marks(
        _marks(exam, demo),
        {demo["rohan"].id: {"status": "PRESENT", "marks": 91, "remarks": "Excellent"}},
        actor_id=demo["teacher_user"].id,
        submit=True,
    )
    exam_service.compute_results(exam, actor_id=demo["admin"].id)

    rows = exam_service.subject_breakdown(exam, demo["rohan"])
    assert len(rows) == 1
    row = rows[0]
    assert row["subject"].code == "MATH"
    assert row["obtained"] == 91
    assert row["percentage"] == 91.0
    assert row["grade"] == "A1"
    assert row["remarks"] == "Excellent"
