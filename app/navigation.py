"""Sidebar navigation per role.

A single definition keeps the three shells consistent while letting each role
have its own information architecture.
"""
from __future__ import annotations

from .models.enums import Role


def _item(label: str, endpoint: str, icon: str, permission: str | None = None, **kwargs):
    return {
        "label": label,
        "endpoint": endpoint,
        "icon": icon,
        "permission": permission,
        "url_kwargs": kwargs,
    }


def staff_nav(role: Role) -> list[dict]:
    """Administrator / Principal / office staff shell."""
    groups = [
        {
            "section": "Overview",
            "items": [_item("Dashboard", "admin.dashboard", "grid")],
        },
        {
            "section": "People",
            "items": [
                _item("Students", "admin_students.index", "users", "students.view"),
                _item("Staff", "admin_staff.index", "id-card", "staff.view"),
                _item("Guardians", "admin_guardians.index", "heart", "parents.manage"),
            ],
        },
        {
            "section": "Academics",
            "items": [
                _item("Classes & Subjects", "admin_academics.index", "book", "academics.manage"),
                _item("Timetable", "admin_timetable.index", "calendar", "timetable.view.all"),
                _item("Attendance", "admin_attendance.index", "check-square", "attendance.mark"),
                _item("Examinations", "admin_exams.index", "clipboard", "exams.manage"),
                _item("Marks & Results", "admin_exams.progress", "award", "exams.manage"),
                _item("Homework", "admin_homework.index", "file-text", "homework.view.all"),
            ],
        },
        {
            "section": "Finance",
            "items": [_item("Fees", "admin_fees.index", "credit-card", "fees.view.all")],
        },
        {
            "section": "Communication",
            "items": [
                _item("Announcements", "admin_announcements.index", "megaphone", "announcements.manage"),
            ],
        },
        {
            "section": "Insights",
            "items": [
                _item("Reports", "admin.reports", "chart", "reports.view"),
                _item("Audit Log", "admin.audit", "shield", "audit.view"),
            ],
        },
        {
            "section": "System",
            "items": [
                _item("School Settings", "admin.settings", "settings", "settings.manage"),
                _item("Users", "admin.users", "key", "users.manage"),
            ],
        },
    ]
    allowed = []
    for group in groups:
        items = [i for i in group["items"] if i["permission"] is None or _allowed(role, i["permission"])]
        if items:
            allowed.append({"section": group["section"], "items": items})
    return allowed


def _allowed(role: Role, permission: str) -> bool:
    from .security.permissions import has_permission

    return has_permission(role, permission)


def teacher_nav() -> list[dict]:
    return [
        {"section": "Today", "items": [_item("Dashboard", "teacher.dashboard", "grid")]},
        {
            "section": "Teaching",
            "items": [
                _item("My Timetable", "teacher.timetable", "calendar"),
                _item("My Classes", "teacher.classes", "users"),
                _item("Attendance", "teacher.attendance", "check-square"),
                _item("Homework", "teacher.homework", "file-text"),
                _item("Study Materials", "teacher.materials", "folder"),
            ],
        },
        {
            "section": "Examinations",
            "items": [_item("Marks Entry", "teacher.marks", "award")],
        },
        {
            "section": "Communication",
            "items": [
                _item("Announcements", "teacher.announcements", "megaphone"),
                _item("Leave", "teacher.leave", "clock"),
                _item("Profile", "teacher.profile", "id-card"),
            ],
        },
    ]


def parent_nav() -> list[dict]:
    return [
        {
            "section": "Overview",
            "items": [
                _item("Home", "parent.home", "home"),
                _item("Announcements", "parent.announcements", "megaphone"),
            ],
        },
        {
            "section": "My Child",
            "items": [
                _item("My Children", "parent.children", "users"),
                _item("Timetable", "parent.timetable", "calendar"),
                _item("Attendance", "parent.attendance", "check-square"),
                _item("Homework", "parent.homework", "file-text"),
                _item("Examinations", "parent.exams", "clipboard"),
                _item("Results", "parent.results", "award"),
                _item("Report Cards", "parent.report_cards", "file-text"),
            ],
        },
        {
            "section": "School",
            "items": [
                _item("Fees", "parent.fees", "credit-card"),
                _item("Leave", "parent.leave", "clock"),
                _item("Profile", "parent.profile", "id-card"),
            ],
        },
    ]


def student_nav() -> list[dict]:
    return [
        {
            "section": "Today",
            "items": [
                _item("Home", "student.home", "home"),
                _item("Announcements", "student.announcements", "megaphone"),
            ],
        },
        {
            "section": "My School",
            "items": [
                _item("My Timetable", "student.timetable", "calendar"),
                _item("My Attendance", "student.attendance", "check-square"),
                _item("Homework", "student.homework", "file-text"),
                _item("Study Materials", "student.materials", "folder"),
                _item("Examinations", "student.exams", "clipboard"),
                _item("Results", "student.results", "award"),
                _item("Report Cards", "student.report_cards", "file-text"),
            ],
        },
        {
            "section": "School",
            "items": [
                _item("My Profile", "student.profile", "id-card"),
            ],
        },
    ]


def nav_for(role: Role) -> list[dict]:
    if role in {
        Role.SUPERUSER,
        Role.PRINCIPAL,
        Role.ADMIN,
        Role.ACCOUNTS,
        Role.ADMISSIONS,
        Role.SUPPORT,
    }:
        return staff_nav(role)
    if role == Role.TEACHER:
        return teacher_nav()
    if role == Role.PARENT:
        return parent_nav()
    return student_nav()
