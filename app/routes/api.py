"""Read-only JSON endpoints that feed the Chart.js dashboards.

Charts are progressive enhancement: every page that uses these also renders the
same numbers as text, so the UI still works without JavaScript.
"""
from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user

from ..extensions import db
from ..models import (
    AttendanceRecord,
    Enrollment,
    Examination,
    ResultSummary,
    SchoolClass,
    Section,
    Student,
)
from ..models.enums import (
    AttendanceStatus,
    EnrollmentStatus,
    ExamStatus,
    StudentStatus,
)
from ..security.guards import permission_required
from ..services import fees as fee_service
from ..services.settings import current_session

bp = Blueprint("api", __name__, url_prefix="/api")


def _session_or_404():
    session = current_session()
    if session is None:
        abort(404)
    return session


@bp.get("/admin/attendance")
@permission_required("reports.view")
def attendance_series():
    session = _session_or_404()
    days = min(max(request.args.get("days", 7, type=int), 2), 30)
    labels: list[str] = []
    percentages: list[float | None] = []
    today = date.today()
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        rows = AttendanceRecord.query.filter_by(date=day).all()
        marked = len(rows)
        present = sum(1 for row in rows if row.status != AttendanceStatus.ABSENT)
        labels.append(day.strftime("%a %d"))
        percentages.append(round(present / marked * 100, 1) if marked else None)
    return jsonify(
        {
            "labels": labels,
            "datasets": [
                {
                    "label": "Attendance %",
                    "data": percentages,
                    "borderColor": "#1D4E89",
                    "backgroundColor": "rgba(29,78,137,.12)",
                    "fill": True,
                    "tension": 0.35,
                    "spanGaps": True,
                }
            ],
        }
    )


@bp.get("/admin/strength")
@permission_required("reports.view")
def strength_series():
    session = _session_or_404()
    rows = (
        db.session.query(SchoolClass.name, db.func.count(Enrollment.id))
        .join(Section, Section.school_class_id == SchoolClass.id)
        .outerjoin(
            Enrollment,
            (Enrollment.section_id == Section.id)
            & (Enrollment.status == EnrollmentStatus.ACTIVE),
        )
        .filter(Section.session_id == session.id, Section.is_active.is_(True))
        .group_by(SchoolClass.id)
        .order_by(SchoolClass.display_order)
        .all()
    )
    return jsonify(
        {
            "labels": [row[0] for row in rows],
            "datasets": [
                {
                    "label": "Students",
                    "data": [row[1] for row in rows],
                    "backgroundColor": "#1D4E89",
                    "borderRadius": 6,
                }
            ],
        }
    )


@bp.get("/admin/finance")
@permission_required("reports.view")
def finance_summary():
    session = _session_or_404()
    summary = fee_service.collection_summary(session.id)
    return jsonify(
        {
            "labels": ["Collected", "Outstanding"],
            "datasets": [
                {
                    "data": [summary["paid"], summary["outstanding"]],
                    "backgroundColor": ["#2F855A", "#C05621"],
                    "borderWidth": 0,
                }
            ],
            "summary": summary,
        }
    )


@bp.get("/exams/<int:exam_id>/grades")
@permission_required("analytics.view")
def grade_distribution(exam_id: int):
    exam = db.session.get(Examination, exam_id)
    if exam is None:
        abort(404)
    results = ResultSummary.query.filter_by(examination_id=exam.id).all()
    order = [rule.grade for rule in exam.grading_scale.rules] if exam.grading_scale else []
    counts: dict[str, int] = {}
    for result in results:
        key = result.grade or "—"
        counts[key] = counts.get(key, 0) + 1
    labels = [grade for grade in order if grade in counts] + [
        grade for grade in counts if grade not in order
    ]
    passed = sum(1 for result in results if result.result_status.value == "PASS")
    return jsonify(
        {
            "labels": labels,
            "datasets": [
                {
                    "label": "Students",
                    "data": [counts[grade] for grade in labels],
                    "backgroundColor": "#B7791F",
                    "borderRadius": 6,
                }
            ],
            "summary": {
                "count": len(results),
                "pass": passed,
                "fail": len(results) - passed,
                "pass_rate": round(passed / len(results) * 100, 1) if results else 0,
            },
        }
    )


@bp.get("/attendance/me")
def my_attendance():
    """Small sparkline dataset for the student portal."""
    if current_user.role.value != "STUDENT" or current_user.student is None:
        abort(403)
    rows = (
        AttendanceRecord.query.filter_by(student_id=current_user.student.id)
        .order_by(AttendanceRecord.date.desc())
        .limit(30)
        .all()
    )
    rows.reverse()
    return jsonify(
        {
            "labels": [row.date.strftime("%d %b") for row in rows],
            "datasets": [
                {
                    "label": "Present",
                    "data": [row.present_value for row in rows],
                    "borderColor": "#2F855A",
                    "backgroundColor": "rgba(47,133,90,.12)",
                    "fill": True,
                    "tension": 0.3,
                }
            ],
        }
    )
