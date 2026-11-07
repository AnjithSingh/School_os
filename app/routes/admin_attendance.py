"""Attendance overview, marking and monthly registers."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..models import Section
from ..models.enums import AttendanceStatus
from ..security.guards import permission_required
from ..services import academics
from ..services import attendance as attendance_service
from ..services.settings import current_session

bp = Blueprint("admin_attendance", __name__, url_prefix="/admin/attendance")


@bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if current_user.scope.value != "STAFF":
        abort(403)


def _parse_date(value: str | None, fallback: date | None = None) -> date:
    if value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    return fallback or date.today()


@bp.route("/")
@permission_required("attendance.mark")
def index():
    session = current_session()
    if session is None:
        flash("Create an academic year first.", "error")
        return redirect(url_for("admin.dashboard"))
    on_date = _parse_date(request.args.get("date"))
    overview = attendance_service.overview_for_date(on_date, session.id)
    sections = Section.query.filter_by(session_id=session.id, is_active=True).all()
    return render_template(
        "admin/attendance/index.html",
        overview=overview,
        on_date=on_date,
        sections=sections,
    )


@bp.route("/mark")
@permission_required("attendance.mark")
def mark():
    session = current_session()
    section_id = request.args.get("section_id", type=int)
    on_date = _parse_date(request.args.get("date"))
    sections = Section.query.filter_by(session_id=session.id, is_active=True).all()
    if section_id:
        section = db.session.get(Section, section_id)
        if section is None:
            abort(404)
    else:
        section = sections[0] if sections else None

    if section is None:
        flash("Create a section before marking attendance.", "error")
        return redirect(url_for("admin_attendance.index"))

    enrollments = attendance_service.enrolled_students(section.id)
    records = attendance_service.existing_records(section.id, on_date)
    holiday = attendance_service.is_holiday(session.id, on_date)
    return render_template(
        "admin/attendance/mark.html",
        section=section,
        sections=sections,
        enrollments=enrollments,
        records=records,
        on_date=on_date,
        holiday=holiday,
        statuses=list(AttendanceStatus),
    )


@bp.post("/mark")
@permission_required("attendance.mark")
def save():
    section = db.get_or_404(Section, request.form.get("section_id", type=int))
    on_date = _parse_date(request.form.get("date"))
    entries = {}
    remarks = {}
    for key, value in request.form.items():
        if key.startswith("status_"):
            try:
                student_id = int(key.split("_", 1)[1])
            except ValueError:
                continue
            entries[student_id] = value
        elif key.startswith("remarks_"):
            try:
                remarks[int(key.split("_", 1)[1])] = value
            except ValueError:
                continue

    try:
        result = attendance_service.save_section_attendance(
            section=section,
            on_date=on_date,
            entries=entries,
            remarks=remarks,
            actor_id=current_user.id,
            is_admin=True,
        )
        flash(
            f"Attendance saved — {result['created']} new, {result['updated']} updated.",
            "success",
        )
    except attendance_service.AttendanceError as error:
        db.session.rollback()
        flash(str(error), "error")

    return redirect(
        url_for("admin_attendance.mark", section_id=section.id, date=on_date.isoformat())
    )


@bp.route("/report")
@permission_required("attendance.report")
def report():
    session = current_session()
    section_id = request.args.get("section_id", type=int)
    today = date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month", type=int) or today.month

    sections = Section.query.filter_by(session_id=session.id, is_active=True).all()
    section = db.session.get(Section, section_id) if section_id else (sections[0] if sections else None)
    register = attendance_service.monthly_register(section.id, year, month) if section else None
    return render_template(
        "admin/attendance/report.html",
        sections=sections,
        section=section,
        register=register,
        year=year,
        month=month,
    )
