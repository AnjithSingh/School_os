"""Authorised file delivery.

Uploads never live under ``static/``. Every download passes through this view,
which re-checks the signed-in user's relationship to the stored file.
"""
from __future__ import annotations

from flask import Blueprint, abort, current_app, redirect, send_file, url_for
from flask_login import current_user
from pathlib import Path

from ..extensions import db
from ..models import (
    Announcement,
    Homework,
    ReportCard,
    StoredFile,
    StudyMaterial,
)
from ..models.enums import AnnouncementStatus
from ..security.scoping import (
    can_access_student,
    is_admin_level,
    teacher_section_ids,
    verified_links,
)

bp = Blueprint("files", __name__, url_prefix="/files")

OPEN_CATEGORIES = {"announcements"}


def _guard_login():
    if not current_user.is_authenticated:
        abort(401)


def _staff_can(record: StoredFile) -> bool:
    if is_admin_level():
        return True
    role = current_user.role.value
    if record.uploaded_by_id == current_user.id:
        return True
    if role == "TEACHER":
        if record.category in {"homework", "materials", "submissions", "announcements"}:
            return True
        sections = teacher_section_ids()
        card = ReportCard.query.filter_by(pdf_file_id=record.id).first()
        if card and can_access_student(card.student, permission="academics"):
            return True
        return bool(sections) and record.category in {"leave", "students"}
    if role in {"ACCOUNTS", "ADMISSIONS", "SUPPORT"}:
        return record.category in {
            "announcements",
            "students",
            "student_documents",
            "receipts",
            "general",
        }
    return False


def _announcement_visible(record: StoredFile) -> bool:
    from ..services.communication import visible_announcements

    announcement = Announcement.query.filter_by(attachment_file_id=record.id).first()
    if announcement is None or announcement.status != AnnouncementStatus.PUBLISHED:
        return False
    if is_admin_level():
        return True
    session = announcement.session_id
    match = visible_announcements(current_user, session).filter(
        Announcement.id == announcement.id
    ).first()
    return match is not None


def _guardian_student_ids() -> set[int]:
    return {link.student_id for link in verified_links() if link.student}


def _portal_can(record: StoredFile) -> bool:
    role = current_user.role.value
    student_ids = (
        _guardian_student_ids()
        if role == "PARENT"
        else ({current_user.student.id} if current_user.student else set())
    )
    if not student_ids:
        return False

    if record.category == "announcements" and _announcement_visible(record):
        return True

    if record.category == "report_cards":
        card = ReportCard.query.filter_by(pdf_file_id=record.id).first()
        return bool(card and card.student_id in student_ids and card.pdf_file and card.is_published)

    if record.category == "homework":
        item = Homework.query.filter_by(attachment_file_id=record.id).first()
        if item is None:
            return False
        return any(
            can_access_student(student, permission="homework")
            for student in _students(student_ids)
            if student.current_enrollment
            and student.current_enrollment.section_id == item.section_id
        )

    if record.category in {"materials", "submissions"}:
        material = StudyMaterial.query.filter_by(file_id=record.id).first()
        if material is not None:
            for student in _students(student_ids):
                enrollment = student.current_enrollment
                if enrollment is None:
                    continue
                if material.school_class_id != enrollment.section.school_class_id:
                    continue
                if material.section_id in (None, enrollment.section_id):
                    return True
            return False
        if record.category == "submissions" and record.uploaded_by_id == current_user.id:
            return True

    if record.category == "students":
        for student in _students(student_ids):
            if student.photo_file_id == record.id:
                return True

    return False


def _students(ids: set[int]):
    from ..models import Student

    return Student.query.filter(Student.id.in_(ids)).all() if ids else []


@bp.get("/<file_uuid>")
def serve(file_uuid: str):
    _guard_login()
    record = StoredFile.query.filter_by(uuid=file_uuid).first()
    if record is None or record.is_deleted:
        abort(404)

    allowed = is_admin_level() or _staff_can(record) or _portal_can(record)
    if not allowed:
        abort(403)

    path = Path(record.stored_path)
    if not path.exists():
        abort(404)

    inline = record.is_image or record.mime == "application/pdf"
    return send_file(
        path,
        mimetype=record.mime or "application/octet-stream",
        as_attachment=not inline,
        download_name=record.original_name,
        conditional=True,
        max_age=0,
    )


@bp.get("/id/<file_uuid>")
def inline(file_uuid: str):
    """Inline variant used for avatars and embedded PDF previews."""
    record = StoredFile.query.filter_by(uuid=file_uuid).first()
    if record is None or record.is_deleted:
        abort(404)
    _guard_login()
    if not (is_admin_level() or _staff_can(record) or _portal_can(record)):
        abort(403)
    path = Path(record.stored_path)
    if not path.exists():
        abort(404)
    return send_file(path, mimetype=record.mime or "application/octet-stream", conditional=True)
