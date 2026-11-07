"""School profile, settings and academic session resolution."""
from __future__ import annotations

import json
from typing import Any

from flask import g

from ..extensions import db
from ..models import AcademicSession, AppSetting, School

DEFAULTS: dict[str, Any] = {
    "attendance.absent_policy": "ZERO",  # ZERO | EXCLUDED
    "result.pass_percent": 33.0,
    "result.pass_subject_percent": 33.0,
    "result.max_failures": 0,
    "result.rounding": "HALF_UP",
    "school.working_days": [0, 1, 2, 3, 4, 5],
    "school.period_minutes": 45,
    "school.start_time": "08:00",
    "school.end_time": "14:00",
    "attendance.edit_window_hours": 48,
    "session.timezone": "Asia/Kolkata",
}


def get_school() -> School | None:
    if not hasattr(g, "school"):
        g.school = db.session.query(School).order_by(School.id).first()
    return g.school


def refresh_school() -> School | None:
    g.school = db.session.query(School).order_by(School.id).first()
    return g.school


def require_school() -> School:
    school = get_school()
    if school is None:
        raise RuntimeError("School profile is not configured.")
    return school


def current_session() -> AcademicSession | None:
    if hasattr(g, "current_session"):
        return g.current_session
    session = (
        db.session.query(AcademicSession)
        .filter_by(is_current=True)
        .order_by(AcademicSession.start_date.desc())
        .first()
    )
    if session is None:
        session = (
            db.session.query(AcademicSession)
            .order_by(AcademicSession.start_date.desc())
            .first()
        )
    g.current_session = session
    return session


def refresh_session() -> AcademicSession | None:
    if hasattr(g, "current_session"):
        del g.current_session
    return current_session()


def get_setting(key: str, default: Any = None) -> Any:
    school = get_school()
    if school is None:
        return DEFAULTS.get(key, default)
    row = AppSetting.query.filter_by(school_id=school.id, key=key).first()
    if row is None or row.value_json in (None, ""):
        return DEFAULTS.get(key, default)
    try:
        return json.loads(row.value_json)
    except (ValueError, TypeError):
        return DEFAULTS.get(key, default)


def set_setting(key: str, value: Any, user_id: int | None = None) -> None:
    school = require_school()
    row = AppSetting.query.filter_by(school_id=school.id, key=key).first()
    payload = json.dumps(value)
    if row is None:
        row = AppSetting(school_id=school.id, key=key, value_json=payload, updated_by_id=user_id)
        db.session.add(row)
    else:
        row.value_json = payload
        row.updated_by_id = user_id


def branding() -> dict[str, str]:
    school = get_school()
    return {
        "primary": (school.primary_color if school else None) or "#1D4E89",
        "secondary": (school.secondary_color if school else None) or "#B7791F",
    }
