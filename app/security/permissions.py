"""Single source of truth for what a role may do.

Routes never compare role strings directly; they ask for a permission. That
keeps the matrix readable in one place and makes the authorisation test suite
straightforward to write.
"""
from __future__ import annotations

from ..models.enums import Role

PERMISSIONS: dict[str, str] = {
    "users.manage": "Create and manage user accounts",
    "settings.manage": "School profile, branding and academic settings",
    "session.manage": "Create and switch academic sessions",
    "academics.manage": "Classes, sections, subjects and allocations",
    "students.view": "View student records",
    "students.manage": "Admit, edit, transfer and promote students",
    "students.export": "Export student data",
    "staff.view": "View staff records",
    "staff.manage": "Create and edit staff records",
    "staff.leave.approve": "Approve staff leave",
    "parents.manage": "Manage guardians and student links",
    "guardian.verify": "Verify guardian-student links",
    "attendance.mark": "Mark daily attendance",
    "attendance.edit": "Edit attendance after marking",
    "attendance.view.all": "View attendance across the school",
    "attendance.report": "Generate attendance reports",
    "timetable.view.all": "View any timetable",
    "timetable.manage": "Build and publish timetables",
    "exams.manage": "Create and configure examinations",
    "marks.enter": "Enter marks for assigned subjects",
    "marks.approve": "Approve submitted marks sheets",
    "results.publish": "Publish results and report cards",
    "results.view.all": "View results across the school",
    "analytics.view": "View examination analytics",
    "homework.manage": "Create homework and review submissions",
    "homework.view.all": "View homework across sections",
    "fees.manage": "Configure fee categories and structures",
    "fees.collect": "Collect fees and issue receipts",
    "fees.concessions": "Approve fee concessions",
    "fees.view.all": "View fee records across the school",
    "announcements.manage": "Publish announcements to any audience",
    "announcements.teacher": "Publish announcements to own sections",
    "reports.view": "View and export school reports",
    "audit.view": "View the audit log",
    "leave.approve": "Approve leave applications",
    "leave.apply": "Apply for leave",
}

_ADMIN_ALL = set(PERMISSIONS)

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.SUPERUSER: set(_ADMIN_ALL),
    Role.PRINCIPAL: set(_ADMIN_ALL) - {"users.manage"},
    Role.ADMIN: {
        "settings.manage",
        "session.manage",
        "academics.manage",
        "students.view",
        "students.manage",
        "students.export",
        "staff.view",
        "staff.manage",
        "staff.leave.approve",
        "parents.manage",
        "guardian.verify",
        "attendance.mark",
        "attendance.edit",
        "attendance.view.all",
        "attendance.report",
        "timetable.view.all",
        "timetable.manage",
        "exams.manage",
        "marks.approve",
        "results.publish",
        "results.view.all",
        "analytics.view",
        "homework.view.all",
        "fees.manage",
        "fees.collect",
        "fees.view.all",
        "announcements.manage",
        "reports.view",
        "leave.approve",
    },
    Role.ACCOUNTS: {
        "students.view",
        "fees.manage",
        "fees.collect",
        "fees.view.all",
        "reports.view",
        "timetable.view.all",
        "announcements.manage",
    },
    Role.ADMISSIONS: {
        "students.view",
        "students.manage",
        "students.export",
        "parents.manage",
        "guardian.verify",
        "timetable.view.all",
        "reports.view",
    },
    Role.TEACHER: {
        "students.view",
        "attendance.mark",
        "attendance.edit",
        "attendance.view.all",
        "attendance.report",
        "timetable.view.all",
        "marks.enter",
        "results.view.all",
        "analytics.view",
        "homework.manage",
        "homework.view.all",
        "announcements.teacher",
        "leave.apply",
        "staff.view",
    },
    Role.PARENT: {"leave.apply"},
    Role.SUPPORT: {"students.view", "timetable.view.all"},
    Role.STUDENT: set(),
}


def has_permission(role: Role | str, permission: str) -> bool:
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            return False
    return permission in ROLE_PERMISSIONS.get(role, set())


def permissions_for(role: Role | str) -> set[str]:
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            return set()
    return set(ROLE_PERMISSIONS.get(role, set()))
