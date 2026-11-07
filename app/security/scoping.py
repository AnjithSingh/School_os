"""Row-level scoping.

These helpers answer "may *this* user touch *this specific* record?". They are
called by services before any write and by views before rendering, and they
return false (mapped to 404 by the caller) rather than leaking existence.
"""
from __future__ import annotations

from flask_login import current_user

from ..extensions import db
from ..models import (
    Enrollment,
    GuardianStudentLink,
    Section,
    StaffProfile,
    Student,
    SubjectAllocation,
    User,
)
from ..models.enums import EnrollmentStatus, LinkStatus, Role, StaffType


def current_staff(user: User | None = None) -> StaffProfile | None:
    user = user or current_user
    if not getattr(user, "is_authenticated", False):
        return None
    return getattr(user, "staff_profile", None)


def is_admin_level(user: User | None = None) -> bool:
    user = user or current_user
    return getattr(user, "role", None) in {Role.SUPERUSER, Role.PRINCIPAL, Role.ADMIN}


def teacher_section_ids(user: User | None = None) -> set[int]:
    """Sections a teacher is responsible for (subject teacher or class teacher)."""
    user = user or current_user
    staff = current_staff(user)
    if not staff or staff.staff_type != StaffType.TEACHING:
        return set()

    assigned = {
        row.section_id
        for row in SubjectAllocation.query.filter_by(teacher_id=staff.id).all()
    }
    class_teacher_of = {
        row.id for row in Section.query.filter_by(class_teacher_id=staff.id).all()
    }
    return assigned | class_teacher_of


def section_ids_for(user: User | None = None) -> set[int] | None:
    """None means "all sections" (admin level)."""
    user = user or current_user
    if is_admin_level(user) or getattr(user, "role", None) in {Role.ADMISSIONS, Role.ACCOUNTS}:
        return None
    if getattr(user, "role", None) == Role.TEACHER:
        return teacher_section_ids(user)
    if getattr(user, "role", None) == Role.PARENT:
        return {
            link.student.current_enrollment.section_id
            for link in verified_links(user)
            if link.student and link.student.current_enrollment
        }
    if getattr(user, "role", None) == Role.STUDENT:
        student = getattr(user, "student", None)
        if student and student.current_enrollment:
            return {student.current_enrollment.section_id}
        return set()
    return set()


def can_access_section(section: Section, user: User | None = None) -> bool:
    user = user or current_user
    allowed = section_ids_for(user)
    return allowed is None or section.id in allowed


def assert_section(section: Section | None, user: User | None = None) -> Section:
    from flask import abort

    if section is None or not can_access_section(section, user):
        abort(404)
    return section


# --------------------------------------------------------------------------
# Guardians
# --------------------------------------------------------------------------
GUARDIAN_PERMISSION_MAP = {
    "academics": "can_view_academics",
    "attendance": "can_view_attendance",
    "fees": "can_pay_fees",
    "homework": "can_view_homework",
    "leave": "can_apply_leave",
    "profile": None,
}


def verified_links(user: User | None = None):
    user = user or current_user
    guardian = getattr(user, "guardian", None)
    if not guardian:
        return []
    return [link for link in guardian.links if link.status == LinkStatus.VERIFIED]


def guardian_can(student: Student, permission: str, user: User | None = None) -> bool:
    user = user or current_user
    if getattr(user, "role", None) != Role.PARENT:
        return False
    attribute = GUARDIAN_PERMISSION_MAP.get(permission)
    for link in verified_links(user):
        if link.student_id == student.id:
            if attribute is None:
                return True
            return bool(getattr(link, attribute, False))
    return False


# --------------------------------------------------------------------------
# Students
# --------------------------------------------------------------------------
def can_access_student(student: Student | None, user: User | None = None, permission: str = "profile") -> bool:
    user = user or current_user
    if student is None:
        return False
    role = getattr(user, "role", None)

    if role in {Role.SUPERUSER, Role.PRINCIPAL, Role.ADMIN, Role.ADMISSIONS}:
        return True
    if role == Role.ACCOUNTS:
        return permission in {"profile", "fees"}
    if role == Role.TEACHER:
        enrollment = student.current_enrollment
        if not enrollment:
            return False
        return enrollment.section_id in teacher_section_ids(user)
    if role == Role.PARENT:
        return guardian_can(student, permission, user)
    if role == Role.STUDENT:
        return getattr(user, "student", None) is not None and user.student.id == student.id
    return False


def assert_student(student: Student | None, permission: str = "profile", user: User | None = None) -> Student:
    from flask import abort

    if not can_access_student(student, user or current_user, permission):
        abort(404)
    return student


def accessible_students(user: User | None = None) -> list[Student]:
    """Used by list views; keeps the query honest regardless of URL input."""
    user = user or current_user
    role = getattr(user, "role", None)
    if role in {Role.SUPERUSER, Role.PRINCIPAL, Role.ADMIN, Role.ADMISSIONS, Role.ACCOUNTS}:
        return Student.query.filter(Student.deleted_at.is_(None)).all()
    if role == Role.TEACHER:
        ids = teacher_section_ids(user)
        if not ids:
            return []
        rows = (
            db.session.query(Student)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .filter(Enrollment.section_id.in_(ids), Enrollment.status == EnrollmentStatus.ACTIVE)
            .all()
        )
        return rows
    if role == Role.PARENT:
        return [link.student for link in verified_links(user)]
    if role == Role.STUDENT:
        return [user.student] if getattr(user, "student", None) else []
    return []


def student_ids_for(user: User | None = None) -> set[int]:
    return {s.id for s in accessible_students(user)}
