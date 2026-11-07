"""Reusable authorisation decorators.

Composes with Flask-Login: ``@login_required`` first, then scope, then
permission. Ownership checks (row level) live in :mod:`app.security.scoping`
and are called from services, not decorators, because they need the object.
"""
from __future__ import annotations

from functools import wraps

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user

from ..models.enums import STAFF_ROLES, Role, Scope
from .permissions import has_permission


def _deny(message: str = "You do not have access to that page."):
    flash(message, "error")
    abort(403)


def roles_required(*roles: Role | str):
    allowed = {Role(r) if isinstance(r, str) else r for r in roles}

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.full_path))
            if current_user.role not in allowed:
                _deny()
            return view(*args, **kwargs)

        return wrapped

    return decorator


def scope_required(scope: Scope):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.full_path))
            if current_user.scope != scope:
                # A parent session can never act inside the staff shell and
                # vice-versa: force a clean re-authentication.
                flash("Please sign in again to use that area.", "warning")
                return redirect(url_for("auth.logout", next=request.path))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def permission_required(permission: str):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.full_path))
            if not has_permission(current_user.role, permission):
                _deny()
            return view(*args, **kwargs)

        return wrapped

    return decorator


def staff_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.full_path))
        if current_user.role not in STAFF_ROLES:
            _deny()
        return view(*args, **kwargs)

    return wrapped
