"""Administrator shell: dashboard, settings, reports, audit and user accounts."""
from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_

from ..extensions import db
from ..forms.academics import SessionForm
from ..forms.auth import UserForm
from ..models import (
    AcademicSession,
    AttendanceRecord,
    AuditLog,
    Enrollment,
    ExamType,
    FeePayment,
    GradeScale,
    SchoolClass,
    Section,
    Student,
    User,
)
from ..models.enums import (
    AttendanceStatus,
    EnrollmentStatus,
    ExamStatus,
    Role,
    Scope,
    StudentStatus,
)
from ..security.guards import permission_required
from ..services import auth as auth_service
from ..services import fees as fee_service
from ..services.audit import record
from ..services.bootstrap import seed_reference_data
from ..services.dashboard import admin_overview
from ..services.settings import (
    get_setting,
    refresh_school,
    set_setting,
)
from ..utils.pagination import paginate

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if current_user.scope != Scope.STAFF:
        from flask import abort

        abort(403)


@bp.route("/")
def dashboard():
    return render_template("admin/dashboard.html", data=admin_overview())


@bp.route("/reports")
@permission_required("reports.view")
def reports():
    from ..services.settings import current_session

    session = current_session()
    strength = []
    if session:
        rows = (
            db.session.query(SchoolClass, func.count(Enrollment.id))
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
        strength = [{"class": row[0], "count": row[1]} for row in rows]

    week = []
    for offset in range(6, -1, -1):
        day = date.today() - timedelta(days=offset)
        rows = AttendanceRecord.query.filter_by(date=day).all()
        marked = len(rows)
        present = sum(
            1 for r in rows if r.status in (AttendanceStatus.PRESENT, AttendanceStatus.LATE)
        )
        week.append(
            {
                "label": day.strftime("%a"),
                "percentage": round(present / marked * 100, 1) if marked else 0,
                "marked": marked,
            }
        )

    finance = fee_service.collection_summary(session.id) if session else {}
    return render_template(
        "admin/reports.html", strength=strength, week=week, finance=finance, session=session
    )


@bp.route("/audit")
@permission_required("audit.view")
def audit():
    query = AuditLog.query
    action = request.args.get("action", "").strip()
    entity = request.args.get("entity", "").strip()
    actor = request.args.get("actor", "").strip()
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    if entity:
        query = query.filter(AuditLog.entity_type == entity)
    if actor:
        query = query.join(AuditLog.actor).filter(
            or_(User.username.ilike(f"%{actor}%"), User.full_name.ilike(f"%{actor}%"))
        )
    query = query.order_by(AuditLog.created_at.desc())
    page = paginate(query, per_page=40)
    entities = [
        row[0]
        for row in db.session.query(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type)
    ]
    return render_template(
        "admin/audit.html", page=page, entities=entities, action=action, entity=entity, actor=actor
    )


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
@bp.route("/settings", methods=["GET", "POST"])
@permission_required("settings.manage")
def settings():
    from ..forms.settings import AcademicPolicyForm, SchoolProfileForm

    from ..services.settings import get_school

    school = get_school()
    profile_form = SchoolProfileForm(obj=school)
    policy_form = AcademicPolicyForm()

    if profile_form.save_profile.data and profile_form.validate_on_submit():
        school.name = profile_form.name.data.strip()
        school.short_name = profile_form.short_name.data
        school.address_line1 = profile_form.address_line1.data
        school.city = profile_form.city.data
        school.state = profile_form.state.data
        school.pincode = profile_form.pincode.data
        school.phone = profile_form.phone.data
        school.email = profile_form.email.data
        school.website = profile_form.website.data
        school.principal_name = profile_form.principal_name.data
        school.affiliation_no = profile_form.affiliation_no.data
        school.motto = profile_form.motto.data
        school.primary_color = profile_form.primary_color.data or "#1D4E89"
        school.secondary_color = profile_form.secondary_color.data or "#B7791F"
        record("settings.school_updated", "School", school.id)
        db.session.commit()
        refresh_school()
        flash("School profile updated.", "success")
        return redirect(url_for("admin.settings"))

    if policy_form.save_policy.data and policy_form.validate_on_submit():
        set_setting("result.pass_percent", policy_form.pass_percent.data, current_user.id)
        set_setting(
            "result.pass_subject_percent", policy_form.pass_subject_percent.data, current_user.id
        )
        set_setting("result.max_failures", policy_form.max_failures.data, current_user.id)
        set_setting("attendance.absent_policy", policy_form.absent_policy.data, current_user.id)
        record("settings.policy_updated", "School", school.id)
        db.session.commit()
        flash("Academic policy updated.", "success")
        return redirect(url_for("admin.settings"))

    if request.method == "GET":
        policy_form.pass_percent.data = float(get_setting("result.pass_percent", 33))
        policy_form.pass_subject_percent.data = float(
            get_setting("result.pass_subject_percent", 33)
        )
        policy_form.max_failures.data = int(get_setting("result.max_failures", 0))
        policy_form.absent_policy.data = get_setting("attendance.absent_policy", "ZERO")

    sessions = AcademicSession.query.order_by(AcademicSession.start_date.desc()).all()
    scales = GradeScale.query.order_by(GradeScale.name).all()
    return render_template(
        "admin/settings.html",
        profile_form=profile_form,
        policy_form=policy_form,
        session_form=SessionForm(),
        sessions=sessions,
        scales=scales,
    )


@bp.route("/settings/sessions", methods=["POST"])
@permission_required("session.manage")
def create_session():
    form = SessionForm()
    if form.validate_on_submit():
        if AcademicSession.query.filter_by(name=form.name.data.strip()).first():
            flash("An academic year with that name already exists.", "error")
            return redirect(url_for("admin.settings"))
        if form.start_date.data >= form.end_date.data:
            flash("The end date must be after the start date.", "error")
            return redirect(url_for("admin.settings"))
        session = AcademicSession(
            school_id=current_user.school_id,
            name=form.name.data.strip(),
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            is_current=False,
        )
        db.session.add(session)
        db.session.flush()
        from ..services.academics import ensure_working_days

        ensure_working_days(session.id, session.school_id)
        record("session.created", "AcademicSession", session.id, summary=session.name)
        db.session.commit()
        flash("Academic year created.", "success")
    else:
        flash("Please check the academic year details.", "error")
    return redirect(url_for("admin.settings"))


@bp.route("/settings/sessions/<int:session_id>/current", methods=["POST"])
@permission_required("session.manage")
def set_current_session(session_id: int):
    session = db.session.get(AcademicSession, session_id)
    if session is None:
        flash("Academic year not found.", "error")
    else:
        AcademicSession.query.update({AcademicSession.is_current: False})
        session.is_current = True
        record("session.switched", "AcademicSession", session.id, summary=session.name)
        db.session.commit()
        flash(f"{session.name} is now the current academic year.", "success")
    return redirect(url_for("admin.settings"))


@bp.route("/settings/seed-reference", methods=["POST"])
@permission_required("settings.manage")
def seed_reference():
    seed_reference_data(db.session.get(User, current_user.id).school)
    db.session.commit()
    flash("Default examination types and grading scale checked.", "success")
    return redirect(url_for("admin.settings"))


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
@bp.route("/users")
@permission_required("users.manage")
def users():
    query = User.query.order_by(User.role, User.full_name)
    role = request.args.get("role", "")
    if role:
        query = query.filter(User.role == role)
    page = paginate(query, per_page=25)
    return render_template("admin/users.html", page=page, roles=Role, role=role)


@bp.route("/users/new", methods=["GET", "POST"])
@permission_required("users.manage")
def user_new():
    form = UserForm()
    form.role.choices = [(r.value, r.label) for r in Role]
    if form.validate_on_submit():
        if User.query.filter(func.lower(User.username) == form.username.data.lower()).first():
            flash("That username is already in use.", "error")
        else:
            user = User(
                school_id=current_user.school_id,
                username=form.username.data.strip().lower(),
                email=(form.email.data or "").strip().lower() or None,
                full_name=form.full_name.data.strip(),
                phone=form.phone.data,
                role=Role(form.role.data),
                is_active=form.is_active.data,
                must_change_password=True,
            )
            user.set_password(form.password.data or "ChangeMe!2026")
            db.session.add(user)
            record("user.created", "User", None, summary=user.username)
            db.session.commit()
            flash("User account created. Share the temporary password securely.", "success")
            return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", form=form, user=None)


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@permission_required("users.manage")
def user_edit(user_id: int):
    user = db.get_or_404(User, user_id)
    form = UserForm(obj=user)
    form.role.choices = [(r.value, r.label) for r in Role]
    if form.validate_on_submit():
        user.full_name = form.full_name.data.strip()
        user.email = (form.email.data or "").strip().lower() or None
        user.phone = form.phone.data
        user.role = Role(form.role.data)
        user.is_active = form.is_active.data
        if form.password.data:
            user.set_password(form.password.data)
            user.must_change_password = True
        record("user.updated", "User", user.id, summary=user.username)
        db.session.commit()
        flash("User updated.", "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", form=form, user=user)


@bp.route("/users/<int:user_id>/reset", methods=["POST"])
@permission_required("users.manage")
def user_reset(user_id: int):
    user = db.get_or_404(User, user_id)
    token = auth_service.issue_reset_token(user, current_user.id)
    record("user.reset_issued", "User", user.id)
    db.session.commit()
    return render_template("admin/reset_token.html", user=user, token=token)


@bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@permission_required("users.manage")
def user_toggle(user_id: int):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
    else:
        user.is_active = not user.is_active
        record("user.toggled", "User", user.id, summary=str(user.is_active))
        db.session.commit()
        flash(f"{user.full_name} is now {'active' if user.is_active else 'inactive'}.", "success")
    return redirect(url_for("admin.users"))
