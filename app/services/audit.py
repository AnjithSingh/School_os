"""Audit logging helper.

Successful writes to academic, financial or access-control data call
``record()`` so the school can answer "who changed this, and when?".
"""
from __future__ import annotations

import json
import uuid

from flask import g, has_request_context, request
from flask_login import current_user

from ..extensions import db
from ..models import AuditLog
from .settings import get_school

REDACTED = {"password", "password_hash", "pin", "pin_hash", "token", "token_hash", "secret"}
MAX_FIELD = 400


def request_id() -> str:
    if not has_request_context():
        return "-"
    if not hasattr(g, "request_id"):
        g.request_id = uuid.uuid4().hex[:12]
    return g.request_id


def _clean(payload) -> str | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        payload = {"value": str(payload)}
    safe = {}
    for key, value in payload.items():
        if key.lower() in REDACTED:
            safe[key] = "***"
        elif isinstance(value, (int, float, bool)) or value is None:
            safe[key] = value
        else:
            safe[key] = str(value)[:MAX_FIELD]
    return json.dumps(safe, default=str)


def record(
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    summary: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    actor_id: int | None = None,
) -> AuditLog | None:
    school = get_school()
    if school is None:
        return None

    if actor_id is None and getattr(current_user, "is_authenticated", False):
        actor_id = current_user.id

    log = AuditLog(
        school_id=school.id,
        actor_user_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=(summary or "")[:255] or None,
        before_json=_clean(before),
        after_json=_clean(after),
        ip=(request.remote_addr if has_request_context() else None),
        user_agent=((request.user_agent.string or "")[:255] if has_request_context() else None),
        request_id=request_id(),
    )
    db.session.add(log)
    return log
