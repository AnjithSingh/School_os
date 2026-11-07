"""Authentication: login, lockout and one-time password reset tokens."""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import func, or_

from ..extensions import db
from ..models import LoginAttempt, PasswordResetToken, User
from ..models.base import utcnow

MAX_FAILURES = 5
LOCK_MINUTES = 15
RESET_TTL_MINUTES = 60


def find_user(identifier: str) -> User | None:
    identifier = (identifier or "").strip().lower()
    if not identifier:
        return None
    return User.query.filter(
        or_(func.lower(User.username) == identifier, func.lower(User.email) == identifier)
    ).first()


def authenticate(identifier: str, password: str, ip: str | None = None,
                 user_agent: str | None = None) -> tuple[User | None, str]:
    """Return (user, error_code). Error codes are generic on purpose."""
    user = find_user(identifier)
    error = None

    if user is None:
        error = "invalid"
    elif not user.is_active:
        error = "inactive"
    elif user.is_locked:
        error = "locked"
    elif not user.check_password(password):
        user.register_failure(MAX_FAILURES, LOCK_MINUTES)
        db.session.commit()
        error = "invalid"
    else:
        user.register_success()
        db.session.commit()

    db.session.add(
        LoginAttempt(
            identifier=(identifier or "")[:160],
            user_id=user.id if user else None,
            ip=ip,
            user_agent=(user_agent or "")[:255],
            success=error is None,
            reason=error,
        )
    )
    db.session.commit()
    return (user if error is None else None), error


def issue_reset_token(user: User, created_by_id: int | None = None) -> str:
    """Create a single-use token. Only the hash is stored."""
    raw = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    db.session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=digest,
            expires_at=utcnow() + timedelta(minutes=RESET_TTL_MINUTES),
            created_by_id=created_by_id,
        )
    )
    db.session.commit()
    return raw


def consume_reset_token(raw: str) -> User | None:
    digest = hashlib.sha256((raw or "").encode()).hexdigest()
    token = PasswordResetToken.query.filter_by(token_hash=digest).first()
    if token is None or not token.is_valid:
        return None
    user = db.session.get(User, token.user_id)
    if user is None:
        return None
    token.used_at = utcnow()
    return user


def complete_reset(raw: str, new_password: str) -> User | None:
    user = consume_reset_token(raw)
    if user is None:
        return None
    user.set_password(new_password)
    user.must_change_password = False
    db.session.commit()
    return user


def change_password(user: User, current: str, new: str) -> bool:
    if not user.check_password(current):
        return False
    user.set_password(new)
    db.session.commit()
    return True


def revoke_other_sessions(user: User) -> None:
    """Placeholder for a future session table; documents intent."""
    user.password_changed_at = utcnow()
    db.session.commit()
