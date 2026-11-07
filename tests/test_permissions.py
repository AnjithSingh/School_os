"""Permission matrix and authorisation guard tests."""
from __future__ import annotations

import pytest

from app.models.enums import Role
from app.security.permissions import ROLE_PERMISSIONS, has_permission
from tests.helpers import login, make_exam, sheet_for


@pytest.mark.parametrize(
    ("role", "permission", "expected"),
    [
        (Role.ADMIN, "students.manage", True),
        (Role.ADMIN, "users.manage", False),
        (Role.PRINCIPAL, "users.manage", False),
        (Role.PRINCIPAL, "results.publish", True),
        (Role.SUPERUSER, "users.manage", True),
        (Role.TEACHER, "marks.enter", True),
        (Role.TEACHER, "students.manage", False),
        (Role.TEACHER, "fees.collect", False),
        (Role.ACCOUNTS, "fees.collect", True),
        (Role.ACCOUNTS, "students.manage", False),
        (Role.PARENT, "students.view", False),
        (Role.PARENT, "leave.apply", True),
        (Role.STUDENT, "students.view", False),
        (Role.SUPPORT, "timetable.view.all", True),
        (Role.SUPPORT, "students.manage", False),
    ],
)
def test_permission_matrix(role, permission, expected):
    assert has_permission(role, permission) is expected


def test_unknown_permission_is_denied_for_every_role():
    for role in Role:
        assert has_permission(role, "does.not.exist") is False


def test_every_role_has_a_defined_permission_set():
    assert set(ROLE_PERMISSIONS) == set(Role)


def test_unauthenticated_staff_page_redirects_to_login(client, demo):
    response = client.get("/admin/students/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_teacher_cannot_open_administration(client, demo):
    login(client, "teacher", "Teacher@12345")
    # Teachers may browse the student directory (students.view) but cannot
    # create students or manage accounts.
    assert client.get("/admin/students/").status_code == 200
    assert client.get("/admin/students/new").status_code == 403
    assert client.get("/admin/users").status_code == 403


def test_teacher_can_open_own_portal(client, demo):
    login(client, "teacher", "Teacher@12345")
    assert client.get("/teacher/").status_code == 200


def test_accounts_staff_cannot_manage_students(client, demo):
    # The demo fixture has no accounts user; use an admin-created one instead.
    from app.extensions import db
    from app.models import User
    from app.models.enums import Role as R

    user = User(
        school_id=demo["school"].id,
        username="accounts",
        full_name="Aarti Accounts",
        role=R.ACCOUNTS,
        is_active=True,
    )
    user.set_password("Accounts@12345")
    db.session.add(user)
    db.session.commit()

    login(client, "accounts", "Accounts@12345")
    assert client.get("/admin/fees/").status_code == 200
    assert client.get("/admin/students/new").status_code == 403


def test_parent_cannot_reach_staff_or_admin_pages(client, demo):
    login(client, "parent", "Parent@12345", endpoint="/parent/login")
    assert client.get("/admin/").status_code == 403
    assert client.get("/teacher/").status_code == 403


def test_student_cannot_reach_parent_or_admin_pages(client, demo):
    login(client, "student", "Student@12345", endpoint="/student/login")
    assert client.get("/admin/").status_code == 403
    assert client.get("/parent/").status_code == 403
    assert client.get("/student/").status_code == 200


def test_parent_cannot_read_another_family_child(client, demo):
    from app.services import students as student_service

    outsider = student_service.create_student(
        school_id=demo["school"].id,
        session=demo["session"],
        first_name="Nina",
        last_name="Outsider",
        section=demo["section"],
        roll_no=3,
        actor_id=demo["admin"].id,
    )
    from app.extensions import db

    db.session.commit()

    login(client, "parent", "Parent@12345", endpoint="/parent/login")
    response = client.get(f"/parent/children/{outsider.id}/results")
    assert response.status_code == 404


def test_guardian_link_permission_is_enforced(client, demo):
    from app.extensions import db
    from app.models import GuardianStudentLink

    link = GuardianStudentLink.query.filter_by(
        guardian_id=demo["guardian"].id, student_id=demo["meera"].id
    ).one()
    link.can_view_academics = False
    db.session.commit()

    login(client, "parent", "Parent@12345", endpoint="/parent/login")
    assert client.get(f"/parent/children/{demo['meera'].id}/results").status_code == 403
    # Rohan's link still allows results.
    assert client.get(f"/parent/children/{demo['rohan'].id}/results").status_code == 200


def test_student_cannot_read_a_report_card_belonging_to_someone_else(client, demo):
    from app.services.exams import compute_results, generate_report_card, save_marks

    exam = make_exam(demo)
    sheet = sheet_for(exam, demo["section"], demo["subjects"]["maths"].id)
    save_marks(
        sheet,
        {demo["meera"].id: {"status": "PRESENT", "marks": 80}},
        actor_id=demo["teacher_user"].id,
    )
    compute_results(exam, actor_id=demo["admin"].id)
    card = generate_report_card(exam, demo["meera"], actor_id=demo["admin"].id)

    login(client, "student", "Student@12345", endpoint="/student/login")
    assert client.get(f"/student/report-cards/{card.id}.pdf").status_code == 404
