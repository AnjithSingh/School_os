"""Daily attendance marking, editing and reporting."""
from __future__ import annotations

from datetime import date

from flask import current_app

from sqlalchemy import func

from ..extensions import db
from ..models import AttendanceRecord, Enrollment, Holiday
from ..models.base import utcnow
from ..models.enums import AttendanceStatus, EnrollmentStatus
from .audit import record


class AttendanceError(Exception):
    pass


def enrolled_students(section_id: int):
    return (
        Enrollment.query.filter_by(section_id=section_id, status=EnrollmentStatus.ACTIVE)
        .join(Enrollment.student)
        .order_by(Enrollment.roll_no.is_(None), Enrollment.roll_no, Enrollment.id)
        .all()
    )


def existing_records(section_id: int, on_date: date) -> dict[int, AttendanceRecord]:
    rows = AttendanceRecord.query.filter_by(section_id=section_id, date=on_date).all()
    return {row.student_id: row for row in rows}


def is_holiday(session_id: int, on_date: date) -> bool:
    if on_date.weekday() == 6:
        return True
    return (
        Holiday.query.filter_by(session_id=session_id, date=on_date).first() is not None
    )


def save_section_attendance(
    *,
    section,
    on_date: date,
    entries: dict[int, str],
    remarks: dict[int, str] | None = None,
    actor_id: int,
    is_admin: bool = False,
) -> dict:
    """Idempotent save. Creates missing rows, updates changed ones, audits edits."""
    remarks = remarks or {}
    enrollments = {e.student_id: e for e in enrolled_students(section.id)}
    existing = existing_records(section.id, on_date)
    created = updated = 0

    for student_id, raw_status in entries.items():
        if student_id not in enrollments:
            continue
        try:
            status = AttendanceStatus(raw_status)
        except ValueError:
            raise AttendanceError("Unknown attendance status.")

        record_row = existing.get(student_id)
        note = (remarks.get(student_id) or "").strip() or None

        if record_row is None:
            db.session.add(
                AttendanceRecord(
                    school_id=section.school_id,
                    student_id=student_id,
                    enrollment_id=enrollments[student_id].id,
                    section_id=section.id,
                    date=on_date,
                    status=status,
                    remarks=note,
                    marked_by_id=actor_id,
                    marked_at=utcnow(),
                )
            )
            created += 1
        elif record_row.status != status or record_row.remarks != note:
            if not is_admin and record_row.marked_by_id != actor_id:
                raise AttendanceError(
                    "This attendance was marked by someone else. Ask an administrator to edit it."
                )
            before = {"status": record_row.status.value, "remarks": record_row.remarks}
            record_row.status = status
            record_row.remarks = note
            record_row.updated_by_id = actor_id
            record("attendance.edited", "AttendanceRecord", record_row.id,
                   before=before, after={"status": status.value, "remarks": note},
                   actor_id=actor_id)
            updated += 1

    db.session.commit()
    return {"created": created, "updated": updated, "total": len(entries)}


def section_day_summary(section_id: int, on_date: date) -> dict:
    rows = AttendanceRecord.query.filter_by(section_id=section_id, date=on_date).all()
    counts = {status.value: 0 for status in AttendanceStatus}
    for row in rows:
        counts[row.status.value] += 1
    total = len(rows)
    present_units = sum(
        {
            AttendanceStatus.PRESENT: 1.0,
            AttendanceStatus.LATE: 1.0,
            AttendanceStatus.EXCUSED: 1.0,
            AttendanceStatus.HALF_DAY: 0.5,
            AttendanceStatus.ABSENT: 0.0,
        }[row.status]
        for row in rows
    )
    return {
        "counts": counts,
        "total": total,
        "present_units": present_units,
        "percentage": round(present_units / total * 100, 1) if total else None,
        "absent": [row for row in rows if row.status == AttendanceStatus.ABSENT],
    }


def student_summary(student_id: int, session_id: int | None = None) -> dict:
    from ..models import AcademicSession

    query = AttendanceRecord.query.filter_by(student_id=student_id)
    if session_id:
        session = db.session.get(AcademicSession, session_id)
        if session:
            query = query.filter(
                AttendanceRecord.date >= session.start_date,
                AttendanceRecord.date <= session.end_date,
            )
    rows = query.order_by(AttendanceRecord.date.desc()).all()
    counts = {status.value: 0 for status in AttendanceStatus}
    for row in rows:
        counts[row.status.value] += 1
    total = len(rows)
    present_units = sum(
        {
            AttendanceStatus.PRESENT: 1.0,
            AttendanceStatus.LATE: 1.0,
            AttendanceStatus.EXCUSED: 1.0,
            AttendanceStatus.HALF_DAY: 0.5,
            AttendanceStatus.ABSENT: 0.0,
        }[row.status]
        for row in rows
    )
    return {
        "rows": rows,
        "counts": counts,
        "total": total,
        "percentage": round(present_units / total * 100, 1) if total else None,
        "present_units": present_units,
    }


def monthly_register(section_id: int, year: int, month: int) -> dict:
    """Per-student, per-day matrix plus totals for the monthly register."""
    from calendar import monthrange

    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    enrollments = enrolled_students(section_id)
    rows = (
        AttendanceRecord.query.filter(
            AttendanceRecord.section_id == section_id,
            AttendanceRecord.date >= first,
            AttendanceRecord.date <= last,
        )
        .all()
    )
    lookup: dict[tuple[int, date], AttendanceRecord] = {
        (row.student_id, row.date): row for row in rows
    }
    days = [date(year, month, d) for d in range(1, last.day + 1)]
    matrix = []
    for enrollment in enrollments:
        cells = []
        present = 0.0
        marked = 0
        for day in days:
            row = lookup.get((enrollment.student_id, day))
            cells.append(row)
            if row:
                marked += 1
                present += row.present_value
        matrix.append(
            {
                "enrollment": enrollment,
                "cells": cells,
                "marked": marked,
                "present": present,
                "percentage": round(present / marked * 100, 1) if marked else None,
            }
        )
    return {"days": days, "matrix": matrix, "first": first, "last": last}


def overview_for_date(on_date: date, session_id: int) -> dict:
    from ..models import Section

    sections = Section.query.filter_by(session_id=session_id, is_active=True).all()
    per_section = []
    totals = {status.value: 0 for status in AttendanceStatus}
    for section in sections:
        summary = section_day_summary(section.id, on_date)
        per_section.append({"section": section, "summary": summary})
        for key, value in summary["counts"].items():
            totals[key] += value
    marked_total = sum(totals.values())
    present_units = (
        totals["PRESENT"] + totals["LATE"] + totals["EXCUSED"] + totals["HALF_DAY"] * 0.5
    )
    return {
        "date": on_date,
        "sections": per_section,
        "totals": totals,
        "marked_total": marked_total,
        "percentage": round(present_units / marked_total * 100, 1) if marked_total else None,
    }
