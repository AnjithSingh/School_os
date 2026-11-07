"""School OS application factory."""
from __future__ import annotations

import logging
import os
import sqlite3
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, logout_user
from flask_wtf.csrf import CSRFError
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.exceptions import HTTPException

from config import get_config

from .extensions import csrf, db, limiter, login_manager, migrate
from .utils.dates import fmt_date, fmt_datetime, fmt_time, fmt_time12, relative_time, weekday_name
from .utils.money import format_money, format_percent

__version__ = "1.0.0"


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ARG001
    """SQLite ignores foreign keys unless asked, and readers block on writers
    without WAL. Both settings are mandatory for data integrity."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))

    _ensure_directories(app)
    _init_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_template_helpers(app)
    _register_hooks(app)
    _register_cli(app)
    _configure_logging(app)

    return app


def _ensure_directories(app: Flask) -> None:
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    for key in ("UPLOAD_FOLDER", "BACKUP_FOLDER", "LOG_FOLDER"):
        Path(app.config[key]).mkdir(parents=True, exist_ok=True)


def _init_extensions(app: Flask) -> None:
    from . import models  # noqa: F401  (registers metadata)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        from .models import User

        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    @login_manager.unauthorized_handler
    def unauthorized():
        target = request.full_path if request.query_string else request.path
        if request.path.startswith("/parent"):
            return redirect(url_for("auth.parent_login", next=target))
        if request.path.startswith("/student"):
            return redirect(url_for("auth.student_login", next=target))
        return redirect(url_for("auth.login", next=target))


def _register_blueprints(app: Flask) -> None:
    from .routes.admin import bp as admin_bp
    from .routes.admin_academics import bp as admin_academics_bp
    from .routes.admin_announcements import bp as admin_announcements_bp
    from .routes.admin_attendance import bp as admin_attendance_bp
    from .routes.admin_exams import bp as admin_exams_bp
    from .routes.admin_fees import bp as admin_fees_bp
    from .routes.admin_guardians import bp as admin_guardians_bp
    from .routes.admin_homework import bp as admin_homework_bp
    from .routes.admin_staff import bp as admin_staff_bp
    from .routes.admin_students import bp as admin_students_bp
    from .routes.admin_timetable import bp as admin_timetable_bp
    from .routes.api import bp as api_bp
    from .routes.auth import bp as auth_bp
    from .routes.files import bp as files_bp
    from .routes.parent import bp as parent_bp
    from .routes.student import bp as student_bp
    from .routes.teacher import bp as teacher_bp

    for blueprint in (
        auth_bp,
        admin_bp,
        admin_students_bp,
        admin_staff_bp,
        admin_guardians_bp,
        admin_academics_bp,
        admin_attendance_bp,
        admin_timetable_bp,
        admin_exams_bp,
        admin_fees_bp,
        admin_homework_bp,
        admin_announcements_bp,
        teacher_bp,
        parent_bp,
        student_bp,
        files_bp,
        api_bp,
    ):
        app.register_blueprint(blueprint)


def _register_template_helpers(app: Flask) -> None:
    from markupsafe import Markup, escape

    from .navigation import nav_for
    from .security.permissions import has_permission
    from .services.settings import branding, current_session, get_school

    def url_with_page(number: int) -> str:
        args = request.args.to_dict(flat=True)
        args["page"] = number
        return url_for(request.endpoint, **(request.view_args or {}), **args)

    # Macros are imported without context, so helpers used inside them must be
    # registered as environment globals rather than context variables.
    app.jinja_env.globals["url_with_page"] = url_with_page

    @app.context_processor
    def inject_globals():  # pragma: no cover - exercised via templates
        school = None
        session_obj = None
        unread = 0
        try:
            school = get_school()
            session_obj = current_session()
            if getattr(current_user, "is_authenticated", False):
                from .models import Notification

                unread = (
                    Notification.query.filter_by(user_id=current_user.id, read_at=None).count()
                )
        except Exception:  # database not ready during first-run setup
            school = None

        nav = []
        if getattr(current_user, "is_authenticated", False):
            nav = nav_for(current_user.role)

        def _has(permission: str) -> bool:
            if not getattr(current_user, "is_authenticated", False):
                return False
            return has_permission(current_user.role, permission)

        return {
            "school": school,
            "current_session": session_obj,
            "unread_notifications": unread,
            "nav": nav,
            "brand": branding(),
            "app_version": __version__,
            "today": __import__("datetime").date.today(),
            "url_with_page": url_with_page,
            "has_permission": _has,
        }

    app.jinja_env.filters["money"] = format_money
    app.jinja_env.filters["percent"] = format_percent
    app.jinja_env.filters["d"] = fmt_date
    app.jinja_env.filters["dt"] = fmt_datetime
    app.jinja_env.filters["t"] = fmt_time
    app.jinja_env.filters["t12"] = fmt_time12
    app.jinja_env.filters["ago"] = relative_time
    app.jinja_env.filters["weekday"] = weekday_name

    @app.template_filter("text")
    def _text(value):
        """Escape then convert newlines — safe multi-line plain text."""
        if not value:
            return ""
        return Markup(str(escape(value)).replace("\n", "<br>"))

    @app.template_filter("initials")
    def _initials(value):
        parts = [p for p in str(value or "").split() if p]
        if not parts:
            return "?"
        return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def _register_hooks(app: Flask) -> None:
    from .services.audit import request_id
    from .services.settings import get_school

    @app.before_request
    def _before():
        from flask_wtf.csrf import generate_csrf

        session.setdefault("_auth_scope_seen", True)
        generate_csrf()  # ensures a token exists for meta tag / fetch calls
        request_id()
        try:
            school = get_school()
        except Exception:
            school = None

        if getattr(current_user, "is_authenticated", False) and not current_user.is_active:
            logout_user()
            flash("Your account has been deactivated. Please contact the school office.", "error")
            return redirect(url_for("auth.login"))

        exempt = {"auth.setup", "auth.login", "auth.parent_login", "auth.student_login", "static"}
        if school is None and request.endpoint not in exempt:
            if request.path.startswith("/api"):
                return {"error": "setup required"}, 503
            return redirect(url_for("auth.setup"))

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'",
        )
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    @app.teardown_request
    def _teardown(exc):
        if exc is not None:
            db.session.rollback()


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(400)
    def bad_request(error):
        return render_template("errors/400.html"), 400

    @app.errorhandler(401)
    def unauthorized(error):
        return render_template("errors/401.html"), 401

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(error):
        flash("That file is too large. The maximum upload size is 10 MB.", "error")
        return render_template("errors/413.html"), 413

    @app.errorhandler(429)
    def rate_limited(error):
        return render_template("errors/429.html"), 429

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return render_template("errors/csrf.html", reason=error.description), 400

    @app.errorhandler(Exception)
    def unhandled(error):
        if isinstance(error, HTTPException):
            return error
        app.logger.exception("Unhandled error: %s", error)
        db.session.rollback()
        return render_template("errors/500.html"), 500


def _configure_logging(app: Flask) -> None:
    if app.config.get("TESTING"):
        return
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    log_path = Path(app.config["LOG_FOLDER"]) / "school_os.log"
    handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    if app.config.get("DEBUG"):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        app.logger.addHandler(console)
    app.logger.setLevel(logging.INFO)


def _register_cli(app: Flask) -> None:
    from .cli import register_cli

    register_cli(app)
