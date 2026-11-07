"""Authentication flows and portal scope separation."""
from __future__ import annotations

from app.extensions import db
from tests.helpers import login


def test_login_page_renders(client, demo):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"Sign in" in response.data or b"sign in" in response.data


def test_setup_is_closed_once_a_school_exists(client, demo):
    response = client.get("/setup")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_wrong_password_is_rejected_without_a_session(client, demo):
    response = login(client, "admin", "not-the-password")
    assert response.status_code == 200
    assert b"Invalid credentials" in response.data
    # The protected shell is still closed.
    assert client.get("/admin/").status_code == 302


def test_unknown_user_is_rejected(client, demo):
    response = login(client, "nobody", "whatever")
    assert response.status_code == 200
    assert b"Invalid credentials" in response.data


def test_staff_login_redirects_to_admin_dashboard(client, demo):
    response = login(client, "admin", "Admin@12345")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/")
    assert client.get("/admin/").status_code == 200


def test_parent_login_is_separate_and_redirects_to_family_dashboard(client, demo):
    response = login(client, "parent", "Parent@12345", endpoint="/parent/login")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/parent/")
    assert client.get("/parent/").status_code == 200


def test_parent_credentials_are_rejected_on_the_student_login(client, demo):
    response = login(client, "parent", "Parent@12345", endpoint="/student/login")
    assert response.status_code == 200
    assert b"Invalid credentials" in response.data


def test_teacher_credentials_are_rejected_on_the_parent_login(client, demo):
    response = login(client, "teacher", "Teacher@12345", endpoint="/parent/login")
    assert response.status_code == 200
    assert b"Invalid credentials" in response.data


def test_student_login_redirects_to_student_portal(client, demo):
    response = login(client, "student", "Student@12345", endpoint="/student/login")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/student/")
    assert client.get("/student/").status_code == 200


def test_inactive_account_cannot_sign_in(client, demo):
    demo["admin"].is_active = False
    db.session.commit()

    response = login(client, "admin", "Admin@12345")
    assert response.status_code == 200
    assert b"inactive" in response.data.lower()


def test_must_change_password_forces_the_password_screen(client, demo):
    demo["admin"].must_change_password = True
    db.session.commit()

    response = login(client, "admin", "Admin@12345")
    assert response.status_code == 302
    assert "/account/password" in response.headers["Location"]


def test_logout_clears_the_session(client, demo):
    login(client, "admin", "Admin@12345")
    assert client.get("/admin/").status_code == 200

    response = client.get("/logout")
    assert response.status_code == 302
    assert client.get("/admin/").status_code == 302


def test_five_failures_lock_the_account(client, demo):
    for _ in range(5):
        login(client, "admin", "wrong")

    demo["admin"] = db.session.get(type(demo["admin"]), demo["admin"].id)
    assert demo["admin"].is_locked is True

    response = login(client, "admin", "Admin@12345")
    assert response.status_code == 200
    assert b"temporarily locked" in response.data.lower()
