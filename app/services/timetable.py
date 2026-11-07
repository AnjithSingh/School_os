"""Timetable building, conflict detection and dated substitutions."""
from __future__ import annotations

from datetime import date, time, timedelta

from sqlalchemy import and_, or_

from ..extensions import db
from ..models import (
    StaffProfile,
    Subject,
    SubjectAllocation,
    Timetable,
    TimetableChange,
    TimetableEntry,
    TimetablePeriod,
)
from ..models.base import utcnow
from ..models.enums import ChangeType, PeriodKind, TimetableStatus
from .audit import record

DEFAULT_PERIODS = [
    (1, "P1", time(8, 0), time(8, 45), PeriodKind.CLASS),
    (2, "P2", time(8, 45), time(9, 30), PeriodKind.CLASS),
    (3, "Break", time(9, 30), time(9, 45), PeriodKind.BREAK),
    (4, "P3", time(9, 45), time(10, 30), PeriodKind.CLASS),
    (5, "P4", time(10, 30), time(11, 15), PeriodKind.CLASS),
    (6, "Lunch", time(11, 15), time(11, 45), PeriodKind.LUNCH),
    (7, "P5", time(11, 45), time(12, 30), PeriodKind.CLASS),
    (8, "P6", time(12, 30), time(13, 15), PeriodKind.CLASS),
    (9, "P7", time(13, 15), time(14, 0), PeriodKind.CLASS),
    (10, "P8", time(14, 0), time(14, 45), PeriodKind.CLASS),
]


class TimetableConflict(Exception):
    pass


def get_timetable(session_id: int, school_id: int, create: bool = True) -> Timetable | None:
    timetable = (
        Timetable.query.filter_by(session_id=session_id)
        .filter(Timetable.status != TimetableStatus.ARCHIVED)
        .order_by(Timetable.status.desc())
        .first()
    )
    if timetable is None and create:
        timetable = Timetable(
            school_id=school_id, session_id=session_id, name="Master Timetable",
            status=TimetableStatus.DRAFT,
        )
        db.session.add(timetable)
        db.session.flush()
        for seq, label, start, end, kind in DEFAULT_PERIODS:
            db.session.add(
                TimetablePeriod(
                    school_id=school_id,
                    timetable_id=timetable.id,
                    sequence=seq,
                    label=label,
                    start_time=start,
                    end_time=end,
                    kind=kind,
                )
            )
        db.session.commit()
    return timetable


def published_timetable(session_id: int) -> Timetable | None:
    return Timetable.query.filter_by(
        session_id=session_id, status=TimetableStatus.PUBLISHED
    ).first()


def cell_map(timetable: Timetable, section_id: int) -> dict:
    entries = TimetableEntry.query.filter_by(
        timetable_id=timetable.id, section_id=section_id
    ).all()
    return {(entry.weekday, entry.period_id): entry for entry in entries}


def teacher_cell_map(timetable: Timetable, teacher_id: int) -> dict:
    entries = TimetableEntry.query.filter_by(
        timetable_id=timetable.id, teacher_id=teacher_id
    ).all()
    return {(entry.weekday, entry.period_id): entry for entry in entries}


def check_conflict(
    timetable: Timetable,
    section_id: int,
    weekday: int,
    period: TimetablePeriod,
    teacher_id: int | None,
    room: str | None,
    ignore_entry_id: int | None = None,
) -> None:
    if period.kind != PeriodKind.CLASS:
        raise TimetableConflict("Assignments can only be placed in teaching periods.")

    if teacher_id:
        query = TimetableEntry.query.filter_by(
            timetable_id=timetable.id, teacher_id=teacher_id, weekday=weekday, period_id=period.id
        ).filter(TimetableEntry.section_id != section_id)
        if ignore_entry_id:
            query = query.filter(TimetableEntry.id != ignore_entry_id)
        clash = query.first()
        if clash:
            raise TimetableConflict(
                f"{clash.teacher.full_name} is already teaching {clash.section.label} "
                f"in {period.label} on {_weekday(weekday)}."
            )

    if room:
        query = TimetableEntry.query.filter_by(
            timetable_id=timetable.id, room=room, weekday=weekday, period_id=period.id
        ).filter(TimetableEntry.section_id != section_id)
        if ignore_entry_id:
            query = query.filter(TimetableEntry.id != ignore_entry_id)
        clash = query.first()
        if clash:
            raise TimetableConflict(
                f"Room {room} is already used by {clash.section.label} in {period.label}."
            )


def save_cell(
    *,
    timetable: Timetable,
    section_id: int,
    weekday: int,
    period: TimetablePeriod,
    subject: Subject,
    teacher: StaffProfile | None,
    room: str | None,
    actor_id: int | None = None,
) -> TimetableEntry:
    if timetable.status == TimetableStatus.PUBLISHED:
        raise TimetableConflict("The timetable is published. Move it back to draft to edit.")

    check_conflict(timetable, section_id, weekday, period, teacher.id if teacher else None, room)

    entry = TimetableEntry.query.filter_by(
        timetable_id=timetable.id, section_id=section_id, weekday=weekday, period_id=period.id
    ).first()
    if entry is None:
        entry = TimetableEntry(
            school_id=timetable.school_id,
            timetable_id=timetable.id,
            section_id=section_id,
            weekday=weekday,
            period_id=period.id,
            subject_id=subject.id,
            teacher_id=teacher.id if teacher else None,
            room=room,
        )
        db.session.add(entry)
    else:
        entry.subject_id = subject.id
        entry.teacher_id = teacher.id if teacher else None
        entry.room = room
    record("timetable.cell_saved", "TimetableEntry", entry.id,
           summary=f"Section {section_id} {_weekday(weekday)} {period.label}", actor_id=actor_id)
    db.session.commit()
    return entry


def delete_cell(entry: TimetableEntry, actor_id: int | None = None) -> None:
    if entry.timetable.status == TimetableStatus.PUBLISHED:
        raise TimetableConflict("The timetable is published. Move it back to draft to edit.")
    record("timetable.cell_removed", "TimetableEntry", entry.id, actor_id=actor_id)
    db.session.delete(entry)
    db.session.commit()


def validate(timetable: Timetable) -> list[str]:
    issues: list[str] = []
    periods = sorted(timetable.periods, key=lambda p: p.start_time)
    for previous, current in zip(periods, periods[1:]):
        if current.start_time < previous.end_time:
            issues.append(
                f"{current.label} starts before {previous.label} ends — periods overlap."
            )
    for entry in timetable.entries:
        if entry.period.kind != PeriodKind.CLASS:
            issues.append(f"{entry.section.label}: {entry.subject.name} placed in a break.")
        if entry.teacher_id is None:
            issues.append(
                f"{entry.section.label}: {entry.subject.name} in {entry.period.label} has no teacher."
            )
    return issues


def publish(timetable: Timetable, actor_id: int) -> list[str]:
    issues = validate(timetable)
    if issues:
        return issues
    Timetable.query.filter_by(
        session_id=timetable.session_id, status=TimetableStatus.PUBLISHED
    ).filter(Timetable.id != timetable.id).update({"status": TimetableStatus.ARCHIVED})
    timetable.status = TimetableStatus.PUBLISHED
    timetable.published_at = utcnow()
    timetable.published_by_id = actor_id
    record("timetable.published", "Timetable", timetable.id, actor_id=actor_id)
    db.session.commit()
    return []


def reopen(timetable: Timetable, actor_id: int) -> None:
    timetable.status = TimetableStatus.DRAFT
    record("timetable.reopened", "Timetable", timetable.id, actor_id=actor_id)
    db.session.commit()


def section_week(timetable: Timetable, section_id: int) -> dict:
    cells = cell_map(timetable, section_id)
    return {
        weekday: {
            period.id: cells.get((weekday, period.id))
            for period in timetable.periods
        }
        for weekday in range(6)
    }


def teacher_week(timetable: Timetable, teacher_id: int) -> dict:
    cells = teacher_cell_map(timetable, teacher_id)
    return {
        weekday: {
            period.id: cells.get((weekday, period.id))
            for period in timetable.periods
        }
        for weekday in range(6)
    }


def day_entries(timetable: Timetable, section_id: int, on_date: date) -> list[dict]:
    """Returns the day's periods with any published change applied."""
    changes = {
        change.original_entry_id: change
        for change in TimetableChange.query.filter_by(
            section_id=section_id, date=on_date
        ).all()
    }
    cells = cell_map(timetable, section_id)
    result = []
    for period in timetable.periods:
        entry = cells.get((on_date.weekday(), period.id))
        change = changes.get(entry.id) if entry else None
        result.append({"period": period, "entry": entry, "change": change})
    return result


def add_change(
    *,
    section_id: int,
    on_date: date,
    change_type,
    original_entry_id: int | None,
    substitute_teacher_id: int | None,
    new_room: str | None,
    reason: str | None,
    actor_id: int,
) -> TimetableChange:
    change_type = ChangeType(change_type)
    change = TimetableChange(
        school_id=_school_id(section_id),
        date=on_date,
        section_id=section_id,
        original_entry_id=original_entry_id,
        change_type=change_type,
        substitute_teacher_id=substitute_teacher_id,
        new_room=new_room,
        reason=reason,
        created_by_id=actor_id,
        published_at=utcnow(),
    )
    db.session.add(change)
    record("timetable.change", "TimetableChange", None,
           summary=f"{change_type} on {on_date}", actor_id=actor_id)
    db.session.commit()
    return change


def teacher_load(timetable: Timetable, teacher_id: int) -> int:
    return TimetableEntry.query.filter_by(
        timetable_id=timetable.id, teacher_id=teacher_id
    ).count()


def allocation_teacher(section_id: int, subject_id: int) -> StaffProfile | None:
    allocation = SubjectAllocation.query.filter_by(
        section_id=section_id, subject_id=subject_id
    ).first()
    return allocation.teacher if allocation else None


def _weekday(index: int) -> str:
    return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][
        index % 7
    ]


def _school_id(section_id: int) -> int:
    from ..models import Section

    section = db.session.get(Section, section_id)
    return section.school_id
