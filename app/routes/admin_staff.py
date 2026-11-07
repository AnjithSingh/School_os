"""Staff and teacher management."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..forms.people import StaffForm
from ..models import (
    LeaveApplication,
    Section,
    StaffProfile,
    SubjectAllocation,
    User,
)
from ..models.base import utcnow
from ..models.enums import LeaveScope, LeaveStatus, Role, StaffType
from ..security.guards import permission_required
from ..services import academics
from ..services.audit import record
from ..services.settings import current_session
from ..utils.pagination import paginate

bp = Blueprint("admin_staff", __name__, url_prefix="/admin/staff")

ROLE_FOR_STAFF_TYPE = {
    StaffType.TEACHING: Role.TEACHER,
    StaffType.ACCOUNTS: Role.ACCOUNTS,
    StaffType.ADMISSIONS: Role.ADMISSIONS,
    StaffType.ADMIN: Role.ADMIN,
    StaffType.SUPPORT: Role.SUPPORT,
}


@bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if current_user.scope.value != "STAFF":
        abort(403)


@bp.route("/")
@permission_required("staff.view")
def index():
    query = StaffProfile.query.join(StaffProfile.user)
    staff_type = request.args.get("type", "")
    q = request.args.get("q", "").strip()
    if staff_type:
        query = query.filter(StaffProfile.staff_type == staff_type)
    if q:
        needle = f"%{q.lower()}%"
        query = query.filter(
            db.or_(
                User.full_name.ilike(needle),
                StaffProfile.employee_code.ilike(needle),
            )
        )
    page = paginate(query.order_by(StaffProfile.employee_code), per_page=20)
    return render_template(
        "admin/staff/index.html", page=page, staff_type=staff_type, q=q, staff_types=StaffType
    )


@bp.route("/new", methods=["GET", "POST"])
@permission_required("staff.manage")
def create():
    form = StaffForm()
    if request.method == "GET":
        form.joining_date.data = date.today()
    if form.validate_on_submit():
        if StaffProfile.query.filter_by(employee_code=form.employee_code.data.strip()).first():
            flash("That employee ID is already in use.", "error")
        elif not form.username.data or not form.password.data:
            flash("A login username and temporary password are required.", "error")
        elif User.query.filter(
            db.func.lower(User.username) == (form.username.data or "").lower()
        ).first():
            flash("That username is already in use.", "error")
        else:
            staff_type = StaffType(form.staff_type.data)
            user = User(
                school_id=current_user.school_id,
                username=form.username.data.strip().lower(),
                email=(form.email.data or "").strip().lower() or None,
                full_name=form.full_name.data.strip(),
                phone=form.phone.data,
                role=ROLE_FOR_STAFF_TYPE[staff_type],
                must_change_password=True,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()

            profile = StaffProfile(
                school_id=current_user.school_id,
                user_id=user.id,
                employee_code=form.employee_code.data.strip().upper(),
                staff_type=staff_type,
                designation=form.designation.data,
                qualification=form.qualification.data,
                specialisation=form.specialisation.data,
                joining_date=form.joining_date.data,
                employment_status=form.employment_status.data,
                gender=form.gender.data or None,
                dob=form.dob.data,
                phone=form.phone.data,
                address=form.address.data,
            )
            db.session.add(profile)
            record("staff.created", "StaffProfile", None, summary=user.full_name)
            db.session.commit()
            flash(f"{user.full_name} added to staff.", "success")
            return redirect(url_for("admin_staff.index"))
    return render_template("admin/staff/form.html", form=form, staff=None)


@bp.route("/<int:staff_id>")
@permission_required("staff.view")
def profile(staff_id: int):
    from ..services.timetable import get_timetable, published_timetable, teacher_load

    staff = db.get_or_404(StaffProfile, staff_id)
    session = current_session()
    allocations = (
        SubjectAllocation.query.filter_by(teacher_id=staff.id).all() if session else []
    )
    sections = Section.query.filter_by(class_teacher_id=staff.id).all()
    timetable = published_timetable(session.id) if session else None
    load = teacher_load(timetable, staff.id) if timetable else 0
    leave = (
        LeaveApplication.query.filter_by(staff_id=staff.id)
        .order_by(LeaveApplication.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "admin/staff/profile.html",
        staff=staff,
        allocations=allocations,
        sections=sections,
        load=load,
        leave=leave,
    )


@bp.route("/<int:staff_id>/edit", methods=["GET", "POST"])
@permission_required("staff.manage")
def edit(staff_id: int):
    staff = db.get_or_404(StaffProfile, staff_id)
    form = StaffForm(obj=staff)
    if request.method == "GET":
        form.full_name.data = staff.user.full_name
        form.email.data = staff.user.email
        form.username.data = staff.user.username
    if form.validate_on_submit():
        staff.user.full_name = form.full_name.data.strip()
        staff.user.email = (form.email.data or "").strip().lower() or None
        staff.user.phone = form.phone.data
        staff.employee_code = form.employee_code.data.strip().upper()
        staff.staff_type = StaffType(form.staff_type.data)
        staff.designation = form.designation.data
        staff.qualification = form.qualification.data
        staff.specialisation = form.specialisation.data
        staff.joining_date = form.joining_date.data
        staff.employment_status = form.employment_status.data
        staff.gender = form.gender.data or None
        staff.dob = form.dob.data
        staff.phone = form.phone.data
        staff.address = form.address.data
        if form.password.data:
            staff.user.set_password(form.password.data)
            staff.user.must_change_password = True
        record("staff.updated", "StaffProfile", staff.id, summary=staff.user.full_name)
        db.session.commit()
        flash("Staff record updated.", "success")
        return redirect(url_for("admin_staff.profile", staff_id=staff.id))
    return render_template("admin/staff/form.html", form=form, staff=staff)


@bp.route("/leave")
@permission_required("staff.leave.approve")
def leave():
    status = request.args.get("status", "PENDING")
    query = LeaveApplication.query
    if status:
        query = query.filter(LeaveApplication.status == LeaveStatus(status))
    page = paginate(query.order_by(LeaveApplication.created_at.desc()), per_page=20)
    return render_template("admin/staff/leave.html", page=page, status=status,
                           statuses=LeaveStatus, scopes=LeaveScope)


@bp.post("/leave/<int:leave_id>/review")
@permission_required("staff.leave.approve")
def review_leave(leave_id: int):
    application = db.get_or_404(LeaveApplication, leave_id)
    decision = request.form.get("decision", "APPROVED")
    remarks = request.form.get("remarks", "").strip()
    application.status = LeaveStatus(decision)
    application.reviewed_by_id = current_user.id
    application.reviewed_at = utcnow()
    application.review_remarks = remarks
    record("leave.reviewed", "LeaveApplication", application.id, summary=decision)
    db.session.commit()
    flash("Leave application updated.", "success")
    return redirect(url_for("admin_staff.leave", status=request.args.get("status", "PENDING")))
