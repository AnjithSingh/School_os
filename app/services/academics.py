"""Academic structure helpers: sections, subjects and teacher allocations."""
from __future__ import annotations

from sqlalchemy import func

from ..extensions import db
from ..models import (
    ClassSubject,
    SchoolClass,
    Section,
    StaffProfile,
    Subject,
    SubjectAllocation,
    WorkingDay,
)
from ..models.enums import EnrollmentStatus, StaffType


def classes(active_only: bool = True):
    query = SchoolClass.query.order_by(SchoolClass.display_order, SchoolClass.level)
    if active_only:
        query = query.filter_by(is_active=True)
    return query.all()


def sections_for(session_id: int | None, class_id: int | None = None, active_only: bool = True):
    if session_id is None:
        return []
    query = Section.query.filter_by(session_id=session_id)
    if class_id:
        query = query.filter_by(school_class_id=class_id)
    if active_only:
        query = query.filter_by(is_active=True)
    return query.order_by(Section.school_class_id, Section.name).all()


def section_by_id(section_id: int) -> Section | None:
    return db.session.get(Section, section_id)


def section_options(session_id: int, include_empty: bool = True):
    rows = sections_for(session_id)
    options = [("", "Select a section")] if include_empty else []
    options += [(str(s.id), s.label) for s in rows]
    return options


def teacher_options(include_empty: bool = True):
    rows = (
        StaffProfile.query.join(StaffProfile.user)
        .filter(StaffProfile.staff_type == StaffType.TEACHING)
        .order_by(StaffProfile.employee_code)
        .all()
    )
    options = [("", "Select a teacher")] if include_empty else []
    options += [(str(t.id), f"{t.full_name} ({t.employee_code})") for t in rows]
    return options


def subject_options(include_empty: bool = True):
    rows = Subject.query.filter_by(is_active=True).order_by(Subject.display_order, Subject.name).all()
    options = [("", "Select a subject")] if include_empty else []
    options += [(str(s.id), f"{s.name} ({s.code})") for s in rows]
    return options


def class_options(include_empty: bool = True):
    rows = classes()
    options = [("", "Select a class")] if include_empty else []
    options += [(str(c.id), c.name) for c in rows]
    return options


def active_students_in(section_id: int):
    from ..models import Enrollment

    return (
        Enrollment.query.filter_by(section_id=section_id, status=EnrollmentStatus.ACTIVE)
        .join(Enrollment.student)
        .order_by(Enrollment.roll_no.is_(None), Enrollment.roll_no, Enrollment.id)
        .all()
    )


def next_roll_no(section_id: int) -> int:
    from ..models import Enrollment

    current = db.session.query(func.max(Enrollment.roll_no)).filter_by(
        section_id=section_id, status=EnrollmentStatus.ACTIVE
    ).scalar()
    return (current or 0) + 1


def subjects_for_class(session_id: int, class_id: int):
    return (
        ClassSubject.query.filter_by(session_id=session_id, school_class_id=class_id)
        .join(ClassSubject.subject)
        .order_by(Subject.display_order)
        .all()
    )


def allocations_for(session_id: int, section_id: int | None = None, teacher_id: int | None = None):
    query = SubjectAllocation.query.filter_by(session_id=session_id)
    if section_id:
        query = query.filter_by(section_id=section_id)
    if teacher_id:
        query = query.filter_by(teacher_id=teacher_id)
    return query.all()


def working_days(session_id: int) -> list[WorkingDay]:
    return (
        WorkingDay.query.filter_by(session_id=session_id).order_by(WorkingDay.weekday).all()
    )


def ensure_working_days(session_id: int, school_id: int) -> list[WorkingDay]:
    rows = working_days(session_id)
    if rows:
        return rows
    for weekday in range(6):
        db.session.add(
            WorkingDay(
                school_id=school_id,
                session_id=session_id,
                weekday=weekday,
                is_working=weekday < 6,
            )
        )
    db.session.commit()
    return working_days(session_id)
