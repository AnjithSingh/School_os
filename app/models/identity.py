"""Identity, configuration, audit and file-storage models."""
from __future__ import annotations

from pathlib import Path

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from .base import SoftDeleteMixin, TenantMixin, TimestampMixin, enum_column, utcnow
from .enums import Role, Scope, STAFF_ROLES


class School(TimestampMixin, db.Model):
    """The school profile. v1 is a single-school deployment (one row)."""

    __tablename__ = "schools"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    short_name = db.Column(db.String(60), nullable=True)
    code = db.Column(db.String(20), nullable=True)
    # Not a FK: schools.logo_file_id <-> stored_files.school_id would be circular.
    logo_file_id = db.Column(db.Integer, nullable=True)

    address_line1 = db.Column(db.String(200), nullable=True)
    address_line2 = db.Column(db.String(200), nullable=True)
    city = db.Column(db.String(80), nullable=True)
    state = db.Column(db.String(80), nullable=True)
    pincode = db.Column(db.String(12), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    alt_phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(160), nullable=True)
    website = db.Column(db.String(200), nullable=True)
    principal_name = db.Column(db.String(120), nullable=True)
    affiliation_no = db.Column(db.String(80), nullable=True)
    motto = db.Column(db.String(200), nullable=True)

    primary_color = db.Column(db.String(9), default="#1D4E89", nullable=False)
    secondary_color = db.Column(db.String(9), default="#B7791F", nullable=False)
    timezone = db.Column(db.String(64), default="Asia/Kolkata", nullable=False)
    currency = db.Column(db.String(8), default="INR", nullable=False)

    is_demo = db.Column(db.Boolean, default=False, nullable=False)

    @property
    def display_name(self) -> str:
        return self.short_name or self.name

    @property
    def address(self) -> str:
        parts = [
            self.address_line1,
            self.address_line2,
            self.city,
            self.state,
            self.pincode,
        ]
        return ", ".join(p for p in parts if p)

    @property
    def logo(self):
        if not self.logo_file_id:
            return None
        return db.session.get(StoredFile, self.logo_file_id)


class AcademicSession(TimestampMixin, db.Model):
    __tablename__ = "academic_sessions"
    __table_args__ = (
        db.UniqueConstraint("school_id", "name", name="uq_session_school_name"),
        db.Index("ix_session_current", "school_id", "is_current"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False
    )
    name = db.Column(db.String(20), nullable=False)  # e.g. 2026-27
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_current = db.Column(db.Boolean, default=False, nullable=False)
    is_locked = db.Column(db.Boolean, default=False, nullable=False)

    school = db.relationship("School", backref=db.backref("sessions", lazy="dynamic"))

    @property
    def label(self) -> str:
        return f"Academic Year {self.name}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AcademicSession {self.name}>"


class AppSetting(TimestampMixin, db.Model):
    __tablename__ = "app_settings"
    __table_args__ = (db.UniqueConstraint("school_id", "key", name="uq_setting_school_key"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False
    )
    key = db.Column(db.String(80), nullable=False)
    value_json = db.Column(db.Text, nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        db.UniqueConstraint("school_id", "username", name="uq_user_school_username"),
        db.UniqueConstraint("school_id", "email", name="uq_user_school_email"),
        db.Index("ix_user_role_active", "role", "is_active"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False
    )
    email = db.Column(db.String(160), nullable=True)
    username = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = enum_column(Role, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    failed_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    password_changed_at = db.Column(db.DateTime, nullable=True)
    avatar_file_id = db.Column(
        db.Integer, db.ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )

    staff_profile = db.relationship(
        "StaffProfile", back_populates="user", uselist=False, foreign_keys="StaffProfile.user_id"
    )
    guardian = db.relationship(
        "Guardian", back_populates="user", uselist=False, foreign_keys="Guardian.user_id"
    )
    student = db.relationship(
        "Student", back_populates="user", uselist=False, foreign_keys="Student.user_id"
    )

    # --- authentication -------------------------------------------------
    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)
        self.password_changed_at = utcnow()
        self.must_change_password = False

    def check_password(self, raw: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw)

    def register_failure(self, threshold: int = 5, lock_minutes: int = 15) -> None:
        from datetime import timedelta

        self.failed_count = (self.failed_count or 0) + 1
        if self.failed_count >= threshold:
            self.locked_until = utcnow() + timedelta(minutes=lock_minutes)
            self.failed_count = 0

    def register_success(self) -> None:
        self.failed_count = 0
        self.locked_until = None
        self.last_login_at = utcnow()

    @property
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > utcnow())

    # --- authorisation --------------------------------------------------
    @property
    def scope(self) -> Scope:
        if self.role == Role.PARENT:
            return Scope.PARENT
        if self.role == Role.STUDENT:
            return Scope.STUDENT
        return Scope.STAFF

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES

    @property
    def is_admin_level(self) -> bool:
        return self.role in {Role.SUPERUSER, Role.PRINCIPAL, Role.ADMIN}

    @property
    def initials(self) -> str:
        parts = [p for p in (self.full_name or "").split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    def has_permission(self, permission: str) -> bool:
        from ..security.permissions import has_permission

        return has_permission(self.role, permission)

    @property
    def dashboard_endpoint(self) -> str:
        return {
            Role.PARENT: "parent.home",
            Role.STUDENT: "student.home",
            Role.TEACHER: "teacher.dashboard",
        }.get(self.role, "admin.dashboard")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username} ({self.role})>"


class LoginAttempt(db.Model):
    __tablename__ = "login_attempts"
    __table_args__ = (db.Index("ix_login_attempt_identifier", "identifier", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    identifier = db.Column(db.String(160), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    ip = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    success = db.Column(db.Boolean, default=False, nullable=False)
    reason = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (db.Index("ix_reset_token_hash", "token_hash"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = db.Column(db.String(128), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    delivery = db.Column(db.String(40), default="IN_PERSON", nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    is_valid = property(lambda self: self.used_at is None and self.expires_at > utcnow())


class StoredFile(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "stored_files"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(400), nullable=False)
    mime = db.Column(db.String(120), nullable=True)
    size_bytes = db.Column(db.Integer, default=0, nullable=False)
    sha256 = db.Column(db.String(64), nullable=True)
    category = db.Column(db.String(40), default="general", nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    @property
    def absolute_path(self) -> str:
        return str(Path(self.stored_path))

    @property
    def is_image(self) -> bool:
        return (self.mime or "").startswith("image/")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    __table_args__ = (
        db.Index("ix_audit_entity", "entity_type", "entity_id"),
        db.Index("ix_audit_actor", "actor_user_id", "created_at"),
        db.Index("ix_audit_created", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False
    )
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    action = db.Column(db.String(80), nullable=False)
    entity_type = db.Column(db.String(60), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    summary = db.Column(db.String(255), nullable=True)
    before_json = db.Column(db.Text, nullable=True)
    after_json = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    request_id = db.Column(db.String(40), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    actor = db.relationship("User", foreign_keys=[actor_user_id])


class Holiday(TimestampMixin, db.Model):
    __tablename__ = "holidays"
    __table_args__ = (db.UniqueConstraint("session_id", "date", name="uq_holiday_session_date"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(
        db.Integer, db.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("academic_sessions.id", ondelete="CASCADE"), nullable=False
    )
    date = db.Column(db.Date, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    kind = db.Column(db.String(30), default="HOLIDAY", nullable=False)

    session = db.relationship("AcademicSession", backref=db.backref("holidays", lazy="dynamic"))
