"""Shared pytest fixtures.

Every test gets a fresh in-memory database built through the same service layer
the application uses, so the fixtures exercise real validation and audit paths
instead of hand-inserted rows that could drift from production behaviour.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from flask import g

from app import create_app
from app.extensions import db
from app.models import (
    AcademicSession,
    ClassSubject,
    ExamType,
    FeeCategory,
    FeeStructure,
    GradeScale,
    SchoolClass,
    Section,
    StaffProfile,
    Subject,
    SubjectAllocation,
)
from app.models.enums import (
    FeeFrequency,
    Gender,
    Role,
    StaffType,
)
from app.services import bootstrap
from app.services import students as student_service


@pytest.fixture()
def app():
    application = create_app("testing")
    application.config.update(
        SERVER_NAME="localhost",
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=False,
    )

    @application.before_request
    def _reset_login_cache():
        # The fixture keeps one app context alive for the whole test so service
        # calls work outside requests. Flask-Login caches the current user on
        # ``g``, which is app-context scoped, so that cache would otherwise leak
        # between requests (and between test clients) within a single test.
        # Real requests always start with a fresh app context; this restores
        # that isolation for the test harness.
        g.pop("_login_user", None)

    with application.app_context():
        db.create_all()
        yield application
        # The test database is a private in-memory SQLite engine; dropping the
        # schema is unnecessary and fails because SQLite cannot topologically
        # sort the users/stored_files cycle while foreign keys are enforced.
        db.session.remove()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def runner(app):
    return app.test_cli_runner()


@pytest.fixture()
def demo(app):
    """A small but complete school: staff, class, students, guardian and fees."""
    school = bootstrap.create_school(
        name="Test Public School",
        short_name="TPS",
        address_line1="1 Test Road",
        city="Pune",
        state="Maharashtra",
        pincode="411001",
        phone="+91 20 0000 0000",
        email="office@test.example",
    )
    session = AcademicSession.query.filter_by(school_id=school.id, is_current=True).one()

    admin = bootstrap.create_user(
        school=school,
        username="admin",
        password="Admin@12345",
        full_name="Anita Admin",
        role=Role.ADMIN,
        email="admin@test.example",
    )
    principal = bootstrap.create_user(
        school=school,
        username="principal",
        password="Principal@12345",
        full_name="Prakash Principal",
        role=Role.PRINCIPAL,
        email="principal@test.example",
    )
    teacher_user = bootstrap.create_user(
        school=school,
        username="teacher",
        password="Teacher@12345",
        full_name="Tara Teacher",
        role=Role.TEACHER,
        email="teacher@test.example",
    )
    teacher = StaffProfile(
        school_id=school.id,
        user_id=teacher_user.id,
        employee_code="EMP001",
        staff_type=StaffType.TEACHING,
        designation="Class Teacher",
        joining_date=date.today() - timedelta(days=365),
    )
    db.session.add(teacher)

    school_class = SchoolClass(school_id=school.id, level=6, name="Class 6", display_order=1)
    db.session.add(school_class)
    db.session.flush()

    section = Section(
        school_id=school.id,
        session_id=session.id,
        school_class_id=school_class.id,
        name="A",
        room="101",
        class_teacher_id=teacher.id,
    )
    db.session.add(section)
    db.session.flush()

    maths = Subject(school_id=school.id, code="MATH", name="Mathematics", display_order=1)
    science = Subject(school_id=school.id, code="SCI", name="Science", display_order=2)
    db.session.add_all([maths, science])
    db.session.flush()

    db.session.add_all(
        [
            ClassSubject(
                school_id=school.id,
                session_id=session.id,
                school_class_id=school_class.id,
                subject_id=maths.id,
            ),
            ClassSubject(
                school_id=school.id,
                session_id=session.id,
                school_class_id=school_class.id,
                subject_id=science.id,
            ),
            SubjectAllocation(
                school_id=school.id,
                session_id=session.id,
                section_id=section.id,
                subject_id=maths.id,
                teacher_id=teacher.id,
                periods_per_week=6,
            ),
            SubjectAllocation(
                school_id=school.id,
                session_id=session.id,
                section_id=section.id,
                subject_id=science.id,
                teacher_id=teacher.id,
                periods_per_week=5,
            ),
        ]
    )

    student_user = bootstrap.create_user(
        school=school,
        username="student",
        password="Student@12345",
        full_name="Rohan Student",
        role=Role.STUDENT,
        email="student@test.example",
    )

    rohan = student_service.create_student(
        school_id=school.id,
        session=session,
        first_name="Rohan",
        last_name="Student",
        section=section,
        dob=date(2014, 5, 1),
        gender=Gender.MALE,
        roll_no=1,
        actor_id=admin.id,
    )
    rohan.user_id = student_user.id
    meera = student_service.create_student(
        school_id=school.id,
        session=session,
        first_name="Meera",
        last_name="Student",
        section=section,
        dob=date(2014, 8, 12),
        gender=Gender.FEMALE,
        roll_no=2,
        actor_id=admin.id,
    )

    guardian = student_service.create_guardian(
        school_id=school.id,
        full_name="Gita Guardian",
        relationship="Mother",
        phone="+91 90000 00000",
        email="parent@test.example",
        username="parent",
        password="Parent@12345",
        verify=True,
        actor_id=admin.id,
    )
    parent_user = guardian.user
    parent_user.must_change_password = False
    student_service.link_guardian(
        guardian=guardian,
        student=rohan,
        relationship="Mother",
        actor_id=admin.id,
        verify=True,
        is_primary=True,
    )
    student_service.link_guardian(
        guardian=guardian,
        student=meera,
        relationship="Mother",
        actor_id=admin.id,
        verify=True,
    )

    category = FeeCategory(
        school_id=school.id,
        session_id=session.id,
        code="TUITION",
        name="Tuition Fee",
        frequency=FeeFrequency.ANNUAL,
    )
    db.session.add(category)
    db.session.flush()
    structure = FeeStructure(
        school_id=school.id,
        session_id=session.id,
        school_class_id=school_class.id,
        fee_category_id=category.id,
        installment_no=1,
        amount_paise=5_000_000,
        due_date=date.today() + timedelta(days=30),
    )
    db.session.add(structure)

    db.session.commit()

    return {
        "school": school,
        "session": session,
        "admin": admin,
        "principal": principal,
        "teacher_user": teacher_user,
        "teacher": teacher,
        "parent_user": parent_user,
        "guardian": guardian,
        "student_user": student_user,
        "rohan": rohan,
        "meera": meera,
        "school_class": school_class,
        "section": section,
        "subjects": {"maths": maths, "science": science},
        "fee_category": category,
        "fee_structure": structure,
        "exam_type": ExamType.query.filter_by(school_id=school.id, code="FA1").one(),
        "grade_scale": GradeScale.query.filter_by(school_id=school.id, is_default=True).one(),
    }


def login(client, identifier, password, endpoint="/login"):
    """Sign in through the real form so session scope is set correctly."""
    return client.post(
        endpoint,
        data={"identifier": identifier, "password": password},
        follow_redirects=False,
    )
