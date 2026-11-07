"""Authentication routes: first-run setup, login, logout, password change, reset."""
from __future__ import annotations

from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db, limiter
from ..forms.auth import ChangePasswordForm, LoginForm, ResetPasswordForm, SetupForm
from ..models import PasswordResetToken, School, User
from ..models.enums import Role
from ..services import auth as auth_service
from ..services.audit import record
from ..services.bootstrap import create_school, create_user
from ..services.settings import refresh_school

bp = Blueprint("auth", __name__)


def safe_next(target: str | None) -> str | None:
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    if not target.startswith("/") or target.startswith("//"):
        return None
    return target


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if School.query.first() is not None:
        return redirect(url_for("auth.login"))
    form = SetupForm()
    if form.validate_on_submit():
        school = create_school(
            name=form.school_name.data.strip(),
            short_name=(form.school_short_name.data or "").strip() or None,
            city=form.city.data,
            state=form.state.data,
            phone=form.phone.data,
            email=form.school_email.data,
        )
        create_user(
            school=school,
            username=form.username.data,
            password=form.password.data,
            full_name=form.admin_name.data,
            role=Role.SUPERUSER,
            email=form.email.data,
        )
        db.session.commit()
        refresh_school()
        flash("School created. Sign in with the owner account you just made.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/setup.html", form=form)


def _login(scope: Role | None, template: str):
    if current_user.is_authenticated:
        return redirect(url_for(current_user.dashboard_endpoint))
    form = LoginForm()
    if form.validate_on_submit():
        user, error = auth_service.authenticate(
            form.identifier.data,
            form.password.data,
            ip=request.remote_addr,
            user_agent=request.user_agent.string,
        )
        if user is None:
            messages = {
                "locked": "This account is temporarily locked. Try again in a few minutes.",
                "inactive": "This account is inactive. Please contact the school office.",
                "invalid": "Invalid credentials. Please check and try again.",
            }
            flash(messages.get(error, "Unable to sign in."), "error")
        elif scope is not None and user.role != scope:
            flash("Invalid credentials. Please check and try again.", "error")
        else:
            login_user(user, remember=form.remember.data)
            session.permanent = True
            session["auth_scope"] = user.scope.value
            session["active_student_id"] = None
            record("auth.login", "User", user.id, summary=f"{user.username} signed in")
            db.session.commit()
            if user.must_change_password:
                flash("Please choose a new password before continuing.", "warning")
                return redirect(url_for("auth.change_password"))
            target = safe_next(request.args.get("next"))
            return redirect(target or url_for(user.dashboard_endpoint))
    return render_template(template, form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    return _login(None, "auth/login.html")


@bp.route("/parent/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def parent_login():
    return _login(Role.PARENT, "auth/parent_login.html")


@bp.route("/student/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def student_login():
    return _login(Role.STUDENT, "auth/student_login.html")


@bp.route("/logout")
def logout():
    if current_user.is_authenticated:
        record("auth.logout", "User", current_user.id, summary="Signed out")
        db.session.commit()
    logout_user()
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if auth_service.change_password(
            current_user, form.current_password.data, form.new_password.data
        ):
            record("auth.password_changed", "User", current_user.id)
            db.session.commit()
            flash("Your password has been updated.", "success")
            return redirect(url_for(current_user.dashboard_endpoint))
        flash("Your current password is incorrect.", "error")
    return render_template("auth/change_password.html", form=form)


@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    reset = PasswordResetToken.query.filter_by(
        token_hash=auth_service.hashlib.sha256(token.encode()).hexdigest()
    ).first()
    if reset is None or not reset.is_valid:
        return render_template("auth/reset_invalid.html"), 400
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user = auth_service.complete_reset(token, form.password.data)
        if user is None:
            return render_template("auth/reset_invalid.html"), 400
        record("auth.password_reset", "User", user.id, actor_id=user.id)
        db.session.commit()
        flash("Password set. You can now sign in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset.html", form=form)


@bp.route("/notifications")
@login_required
def notifications():
    from ..models import Notification

    rows = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
        .all()
    )
    return render_template("shared/notifications.html", notifications=rows)


@bp.route("/notifications/read", methods=["POST"])
@login_required
def mark_notifications_read():
    from ..models.base import utcnow
    from ..models import Notification

    Notification.query.filter_by(user_id=current_user.id, read_at=None).update(
        {"read_at": utcnow()}
    )
    db.session.commit()
    target = safe_next(request.form.get("next"))
    return redirect(target or url_for("auth.notifications"))


@bp.route("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return redirect(url_for(current_user.dashboard_endpoint))


@bp.route("/account/profile")
@login_required
def account_profile():
    return render_template("shared/account.html")
