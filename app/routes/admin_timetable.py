"""Timetable builder, publishing and substitutions."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..forms.operations import ChangeForm, PeriodForm, TimetableCellForm
from ..models import Section, StaffProfile, Subject, Timetable, TimetableEntry, TimetablePeriod
from ..models.enums import PeriodKind, StaffType
from ..security.guards import permission_required
from ..services import academics
from ..services import timetable as timetable_service
from ..services.audit import record
from ..services.settings import current_session

bp = Blueprint("admin_timetable", __name__, url_prefix="/admin/timetable")


@bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if current_user.scope.value != "STAFF":
        abort(403)


@bp.route("/")
@permission_required("timetable.view.all")
def index():
    session = current_session()
    if session is None:
        flash("Create an academic year first.", "error")
        return redirect(url_for("admin.dashboard"))

    timetable = timetable_service.get_timetable(session.id, current_user.school_id)
    sections = Section.query.filter_by(session_id=session.id, is_active=True).all()
    section_id = request.args.get("section_id", type=int)
    section = db.session.get(Section, section_id) if section_id else (sections[0] if sections else None)

    week = timetable_service.section_week(timetable, section.id) if section else {}
    teachers = StaffProfile.query.join(StaffProfile.user).filter(
        StaffProfile.staff_type == StaffType.TEACHING
    ).all()
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()

    cell_form = TimetableCellForm()
    cell_form.section_id.choices = [(s.id, s.label) for s in sections]
    cell_form.period_id.choices = [
        (p.id, f"{p.label} · {p.start_time:%H:%M}") for p in timetable.class_periods
    ]
    cell_form.subject_id.choices = [(s.id, s.name) for s in subjects]
    cell_form.teacher_id.choices = [(0, "No teacher")] + [
        (t.id, t.full_name) for t in teachers
    ]
    if section:
        cell_form.section_id.data = section.id

    change_form = ChangeForm()
    change_form.section_id.choices = [(s.id, s.label) for s in sections]
    change_form.substitute_teacher_id.choices = [(0, "Select substitute")] + [
        (t.id, t.full_name) for t in teachers
    ]
    entry_choices = [(0, "Select period")]
    if section:
        for entry in TimetableEntry.query.filter_by(
            timetable_id=timetable.id, section_id=section.id
        ).all():
            entry_choices.append(
                (
                    entry.id,
                    f"{['Mon','Tue','Wed','Thu','Fri','Sat'][entry.weekday]} "
                    f"{entry.period.label} · {entry.subject.name}",
                )
            )
    change_form.original_entry_id.choices = entry_choices

    return render_template(
        "admin/timetable/index.html",
        timetable=timetable,
        sections=sections,
        section=section,
        week=week,
        cell_form=cell_form,
        change_form=change_form,
        teachers=teachers,
        subjects=subjects,
        issues=timetable_service.validate(timetable),
        today=date.today(),
    )


@bp.post("/cell")
@permission_required("timetable.manage")
def save_cell():
    session = current_session()
    timetable = timetable_service.get_timetable(session.id, current_user.school_id)
    form = TimetableCellForm()
    form.section_id.choices = [
        (s.id, s.label) for s in Section.query.filter_by(session_id=session.id)
    ]
    form.period_id.choices = [(p.id, p.label) for p in timetable.periods]
    form.subject_id.choices = [(s.id, s.name) for s in Subject.query.all()]
    form.teacher_id.choices = [(0, "None")] + [
        (t.id, t.full_name) for t in StaffProfile.query.all()
    ]
    if not form.validate_on_submit():
        flash("Please complete all timetable fields.", "error")
        return redirect(url_for("admin_timetable.index", section_id=form.section_id.data or None))

    section = db.session.get(Section, form.section_id.data)
    period = db.session.get(TimetablePeriod, form.period_id.data)
    subject = db.session.get(Subject, form.subject_id.data)
    teacher = db.session.get(StaffProfile, form.teacher_id.data) if form.teacher_id.data else None

    try:
        timetable_service.save_cell(
            timetable=timetable,
            section_id=section.id,
            weekday=form.weekday.data,
            period=period,
            subject=subject,
            teacher=teacher,
            room=(form.room.data or "").strip() or None,
            actor_id=current_user.id,
        )
        flash("Slot saved.", "success")
    except timetable_service.TimetableConflict as error:
        db.session.rollback()
        flash(str(error), "error")
    return redirect(url_for("admin_timetable.index", section_id=section.id))


@bp.post("/cell/<int:entry_id>/delete")
@permission_required("timetable.manage")
def delete_cell(entry_id: int):
    entry = db.get_or_404(TimetableEntry, entry_id)
    section_id = entry.section_id
    try:
        timetable_service.delete_cell(entry, current_user.id)
        flash("Slot cleared.", "success")
    except timetable_service.TimetableConflict as error:
        flash(str(error), "error")
    return redirect(url_for("admin_timetable.index", section_id=section_id))


@bp.post("/publish")
@permission_required("timetable.manage")
def publish():
    session = current_session()
    timetable = timetable_service.get_timetable(session.id, current_user.school_id)
    issues = timetable_service.publish(timetable, current_user.id)
    if issues:
        for issue in issues:
            flash(issue, "error")
    else:
        flash("Timetable published. Staff can now see it.", "success")
    return redirect(url_for("admin_timetable.index"))


@bp.post("/reopen")
@permission_required("timetable.manage")
def reopen():
    session = current_session()
    timetable = timetable_service.get_timetable(session.id, current_user.school_id)
    timetable_service.reopen(timetable, current_user.id)
    flash("Timetable moved back to draft.", "info")
    return redirect(url_for("admin_timetable.index"))


@bp.post("/periods")
@permission_required("timetable.manage")
def add_period():
    session = current_session()
    timetable = timetable_service.get_timetable(session.id, current_user.school_id)
    form = PeriodForm()
    if form.validate_on_submit():
        if form.start_time.data >= form.end_time.data:
            flash("The end time must be after the start time.", "error")
        else:
            next_seq = max((p.sequence for p in timetable.periods), default=0) + 1
            db.session.add(
                TimetablePeriod(
                    school_id=current_user.school_id,
                    timetable_id=timetable.id,
                    sequence=next_seq,
                    label=form.label.data.strip(),
                    start_time=form.start_time.data,
                    end_time=form.end_time.data,
                    kind=PeriodKind(form.kind.data),
                )
            )
            db.session.commit()
            flash("Period added.", "success")
    else:
        flash("Please check the period details.", "error")
    return redirect(url_for("admin_timetable.index"))


@bp.post("/changes")
@permission_required("timetable.manage")
def add_change():
    session = current_session()
    form = ChangeForm()
    form.section_id.choices = [(s.id, s.label) for s in Section.query.filter_by(session_id=session.id)]
    form.substitute_teacher_id.choices = [(0, "None")] + [
        (t.id, t.full_name) for t in StaffProfile.query.all()
    ]
    form.original_entry_id.choices = [(0, "None")] + [
        (e.id, f"{e.period.label}") for e in TimetableEntry.query.all()
    ]
    if form.validate_on_submit():
        timetable_service.add_change(
            section_id=form.section_id.data,
            on_date=form.date.data,
            change_type=form.change_type.data,
            original_entry_id=form.original_entry_id.data or None,
            substitute_teacher_id=form.substitute_teacher_id.data or None,
            new_room=form.new_room.data,
            reason=form.reason.data,
            actor_id=current_user.id,
        )
        flash("Timetable change published.", "success")
        return redirect(url_for("admin_timetable.index", section_id=form.section_id.data))
    flash("Please check the change details.", "error")
    return redirect(url_for("admin_timetable.index"))
