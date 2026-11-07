"""Attendance service and register route behaviour."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import AttendanceRecord, User
from app.models.enums import AttendanceStatus, Role
from app.services import attendance as attendance_service
from tests.helpers import login


def _monday(offset_weeks: int = 0) -> date:
    today = date.today()
    days = (7 - today.weekday()) % 7 or 7
    return today + timedelta(days=days + offset_weeks * 7)


def test_save_creates_records_for_enrolled_students(demo):
    day = _monday()
    result = attendance_service.save_section_attendance(
        section=demo["section"],
        on_date=day,
        entries={demo["rohan"].id: "PRESENT", demo["meera"].id: "ABSENT"},
        actor_id=demo["teacher_user"].id,
    )

    assert result == {"created": 2, "updated": 0, "total": 2}
    rows = AttendanceRecord.query.filter_by(section_id=demo["section"].id, date=day).all()
    assert len(rows) == 2
    assert {row.student_id: row.status for row in rows}[demo["rohan"].id] == AttendanceStatus.PRESENT


def test_saving_the_same_register_twice_is_idempotent(demo):
    day = _monday()
    entries = {demo["rohan"].id: "PRESENT", demo["meera"].id: "LATE"}
    attendance_service.save_section_attendance(
        section=demo["section"], on_date=day, entries=entries,
        actor_id=demo["teacher_user"].id,
    )
    second = attendance_service.save_section_attendance(
        section=demo["section"], on_date=day, entries=entries,
        actor_id=demo["teacher_user"].id,
    )

    assert second == {"created": 0, "updated": 0, "total": 2}
    assert AttendanceRecord.query.filter_by(section_id=demo["section"].id, date=day).count() == 2


def test_a_teacher_cannot_edit_another_teachers_register(demo):
    day = _monday()
    attendance_service.save_section_attendance(
        section=demo["section"], on_date=day,
        entries={demo["rohan"].id: "PRESENT"},
        actor_id=demo["teacher_user"].id,
    )

    other = User(
        school_id=demo["school"].id,
        username="teacher2",
        full_name="Tina Other",
        role=Role.TEACHER,
        is_active=True,
    )
    other.set_password("Teacher@12345")
    db.session.add(other)
    db.session.commit()

    with pytest.raises(attendance_service.AttendanceError):
        attendance_service.save_section_attendance(
            section=demo["section"], on_date=day,
            entries={demo["rohan"].id: "ABSENT"},
            actor_id=other.id,
        )


def test_an_administrator_can_correct_a_register(demo):
    day = _monday()
    attendance_service.save_section_attendance(
        section=demo["section"], on_date=day,
        entries={demo["rohan"].id: "PRESENT"},
        actor_id=demo["teacher_user"].id,
    )
    result = attendance_service.save_section_attendance(
        section=demo["section"], on_date=day,
        entries={demo["rohan"].id: "ABSENT"},
        actor_id=demo["admin"].id,
        is_admin=True,
    )

    assert result["updated"] == 1
    row = AttendanceRecord.query.filter_by(student_id=demo["rohan"].id, date=day).one()
    assert row.status == AttendanceStatus.ABSENT


def test_unknown_students_are_ignored_and_invalid_statuses_rejected(demo):
    day = _monday()
    result = attendance_service.save_section_attendance(
        section=demo["section"], on_date=day,
        entries={999_999: "PRESENT"},
        actor_id=demo["admin"].id,
    )
    assert result["total"] == 1
    assert AttendanceRecord.query.count() == 0

    with pytest.raises(attendance_service.AttendanceError):
        attendance_service.save_section_attendance(
            section=demo["section"], on_date=day,
            entries={demo["rohan"].id: "SLEEPING"},
            actor_id=demo["admin"].id,
        )


def test_summary_counts_late_as_present_and_half_day_as_half(demo):
    day = _monday()
    attendance_service.save_section_attendance(
        section=demo["section"], on_date=day,
        entries={demo["rohan"].id: "LATE", demo["meera"].id: "HALF_DAY"},
        actor_id=demo["teacher_user"].id,
    )

    summary = attendance_service.student_summary(demo["rohan"].id, demo["session"].id)
    assert summary["total"] == 1
    assert summary["percentage"] == 100.0

    meera = attendance_service.student_summary(demo["meera"].id, demo["session"].id)
    assert meera["percentage"] == 50.0
    assert meera["counts"]["HALF_DAY"] == 1


def test_section_day_summary_reports_absentees(demo):
    day = _monday()
    attendance_service.save_section_attendance(
        section=demo["section"], on_date=day,
        entries={demo["rohan"].id: "PRESENT", demo["meera"].id: "ABSENT"},
        actor_id=demo["teacher_user"].id,
    )
    summary = attendance_service.section_day_summary(demo["section"].id, day)
    assert summary["total"] == 2
    assert summary["percentage"] == 50.0
    assert [row.student_id for row in summary["absent"]] == [demo["meera"].id]


def test_teacher_can_mark_the_register_through_the_route(client, demo):
    day = _monday()
    login(client, "teacher", "Teacher@12345")

    response = client.post(
        "/teacher/attendance",
        data={
            "section_id": demo["section"].id,
            "date": day.isoformat(),
            f"status_{demo['rohan'].id}": "PRESENT",
            f"status_{demo['meera'].id}": "ABSENT",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert AttendanceRecord.query.filter_by(section_id=demo["section"].id, date=day).count() == 2
