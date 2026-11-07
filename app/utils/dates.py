"""Date and time helpers.

Dates are stored as plain school-local ``date`` objects. Timestamps are stored
as naive UTC and rendered in the school's timezone.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

IST = timezone(timedelta(hours=5, minutes=30))
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def today() -> date:
    return date.today()


def tzinfo(name: str = "Asia/Kolkata"):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return IST


def to_local(dt: datetime | None, tz_name: str = "Asia/Kolkata") -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tzinfo(tz_name))


def fmt_date(value: date | datetime | None, style: str = "medium") -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        value = value.date()
    if style == "short":
        return value.strftime("%d/%m/%Y")
    if style == "iso":
        return value.isoformat()
    if style == "long":
        return f"{value.day} {MONTHS[value.month - 1]} {value.year}"
    return f"{value.day:02d} {MONTHS[value.month - 1][:3]} {value.year}"


def fmt_time(value: time | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%H:%M")


def fmt_time12(value: time | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%I:%M %p").lstrip("0")


def fmt_datetime(value: datetime | None, tz_name: str = "Asia/Kolkata") -> str:
    local = to_local(value, tz_name)
    if not local:
        return "—"
    return local.strftime("%d %b %Y, %I:%M %p").replace(" 0", " ")


def relative_time(value: datetime | None, tz_name: str = "Asia/Kolkata") -> str:
    local = to_local(value, tz_name)
    if not local:
        return "—"
    now = datetime.now(tzinfo(tz_name))
    delta = now - local
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    if seconds < 604800:
        return f"{seconds // 86400} d ago"
    return local.strftime("%d %b %Y")


def weekday_name(value: int | date | datetime) -> str:
    """Return the weekday name for a date, datetime or weekday index."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return WEEKDAYS[value.weekday()]
    return WEEKDAYS[int(value) % 7]


def month_bounds(day: date) -> tuple[date, date]:
    first = day.replace(day=1)
    if first.month == 12:
        nxt = first.replace(year=first.year + 1, month=1)
    else:
        nxt = first.replace(month=first.month + 1)
    return first, nxt - timedelta(days=1)


def date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def month_choices(year: int):
    return [(m, MONTHS[m - 1]) for m in range(1, 13)]
