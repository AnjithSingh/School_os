"""Bootstrap helpers: first-run school creation and default reference data."""
from __future__ import annotations

from datetime import date

from ..extensions import db
from ..models import (
    AcademicSession,
    ExamType,
    GradeRule,
    GradeScale,
    School,
    User,
    WorkingDay,
)
from ..models.enums import Role

DEFAULT_EXAM_TYPES = [
    ("FA1", "Formative Assessment 1", 1, 10, False),
    ("FA2", "Formative Assessment 2", 2, 10, False),
    ("SA1", "Summative Assessment 1", 3, 30, True),
    ("FA3", "Formative Assessment 3", 4, 10, False),
    ("FA4", "Formative Assessment 4", 5, 10, False),
    ("SA2", "Summative Assessment 2", 6, 30, True),
    ("PRE_FINAL", "Pre-Final Examination", 7, 0, False),
    ("FINAL", "Final Examination", 8, 0, True),
]

DEFAULT_GRADES = [
    ("A1", 91, 100, 10.0, "Outstanding"),
    ("A2", 81, 90, 9.0, "Excellent"),
    ("B1", 71, 80, 8.0, "Very Good"),
    ("B2", 61, 70, 7.0, "Good"),
    ("C1", 51, 60, 6.0, "Above Average"),
    ("C2", 41, 50, 5.0, "Average"),
    ("D", 33, 40, 4.0, "Needs Improvement"),
    ("E", 0, 32, 0.0, "Essential Repeat"),
]


def academic_year_for(today: date | None = None) -> tuple[str, date, date]:
    """Indian academic year: April to March."""
    today = today or date.today()
    if today.month >= 4:
        start_year = today.year
    else:
        start_year = today.year - 1
    name = f"{start_year}-{str(start_year + 1)[-2:]}"
    return name, date(start_year, 4, 1), date(start_year + 1, 3, 31)


def create_school(
    *,
    name: str,
    short_name: str | None = None,
    address_line1: str | None = None,
    city: str | None = None,
    state: str | None = None,
    pincode: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    primary_color: str = "#1D4E89",
    secondary_color: str = "#B7791F",
    is_demo: bool = False,
) -> School:
    school = School(
        name=name,
        short_name=short_name or name,
        address_line1=address_line1,
        city=city,
        state=state,
        pincode=pincode,
        phone=phone,
        email=email,
        primary_color=primary_color,
        secondary_color=secondary_color,
        is_demo=is_demo,
    )
    db.session.add(school)
    db.session.flush()

    year_name, start, end = academic_year_for()
    session = AcademicSession(
        school_id=school.id, name=year_name, start_date=start, end_date=end, is_current=True
    )
    db.session.add(session)
    db.session.flush()

    for weekday in range(6):
        db.session.add(
            WorkingDay(
                school_id=school.id,
                session_id=session.id,
                weekday=weekday,
                is_working=weekday < 6,
                is_half_day=False,
            )
        )

    seed_reference_data(school)
    db.session.flush()
    return school


def seed_reference_data(school: School) -> None:
    """Exam types and a default grade scale. Idempotent."""
    existing = {row.code for row in ExamType.query.filter_by(school_id=school.id).all()}
    for code, label, sequence, weight, terminal in DEFAULT_EXAM_TYPES:
        if code in existing:
            continue
        db.session.add(
            ExamType(
                school_id=school.id,
                code=code,
                name=label,
                sequence=sequence,
                default_weight=weight,
                is_terminal=terminal,
            )
        )

    scale = GradeScale.query.filter_by(school_id=school.id, is_default=True).first()
    if scale is None:
        scale = GradeScale(school_id=school.id, name="Default Grading Scale", is_default=True)
        db.session.add(scale)
        db.session.flush()
        for order, (grade, low, high, points, description) in enumerate(DEFAULT_GRADES):
            db.session.add(
                GradeRule(
                    school_id=school.id,
                    grade_scale_id=scale.id,
                    grade=grade,
                    min_percent=float(low),
                    max_percent=float(high),
                    grade_point=points,
                    description=description,
                    sort_order=order,
                )
            )


def create_user(
    *,
    school: School,
    username: str,
    password: str,
    full_name: str,
    role: Role,
    email: str | None = None,
    phone: str | None = None,
    must_change_password: bool = False,
) -> User:
    user = User(
        school_id=school.id,
        username=username.strip().lower(),
        email=(email.strip().lower() if email else None),
        full_name=full_name.strip(),
        role=role,
        phone=phone,
        must_change_password=must_change_password,
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    return user
