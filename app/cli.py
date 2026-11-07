"""Command line commands: database lifecycle, demo data, users and backups."""
from __future__ import annotations

import random
import shutil
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path

import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import func

from .extensions import db
from .models import (
    AcademicSession,
    Announcement,
    AttendanceRecord,
    ClassSubject,
    Enrollment,
    ExamType,
    Examination,
    ExaminationClass,
    ExaminationSubject,
    FeeCategory,
    FeePayment,
    FeeStructure,
    GradeScale,
    Guardian,
    GuardianStudentLink,
    Homework,
    MarksEntrySheet,
    MarksRecord,
    ReportCard,
    ResultSummary,
    School,
    SchoolClass,
    Section,
    StaffProfile,
    Student,
    StudentFee,
    Subject,
    SubjectAllocation,
    Timetable,
    TimetableEntry,
    TimetablePeriod,
    User,
)
from .models.enums import (
    AnnouncementCategory,
    AnnouncementScope,
    AnnouncementStatus,
    AttendanceStatus,
    ConcessionStatus,
    EnrollmentStatus,
    ExamStatus,
    FeeFrequency,
    FeeStatus,
    Gender,
    HomeworkStatus,
    LinkStatus,
    MarkStatus,
    PaymentMethod,
    PeriodKind,
    Role,
    SheetStatus,
    StaffType,
    StudentStatus,
    TimetableStatus,
)
from .services import bootstrap, fees as fee_service, students as student_service
from .services.exams import compute_results, ensure_sheets, generate_report_card, publish
from .services.settings import get_school, refresh_school


def register_cli(app) -> None:
    app.cli.add_command(init_db)
    app.cli.add_command(reset_db)
    app.cli.add_command(create_user_command)
    app.cli.add_command(seed_demo)
    app.cli.add_command(backup_command)
    app.cli.add_command(set_password_command)


@click.command("init-db")
@with_appcontext
def init_db() -> None:
    """Create every table without touching existing data."""
    db.create_all()
    click.echo(f"Database ready — {len(db.metadata.tables)} tables.")


@click.command("reset-db")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@with_appcontext
def reset_db(yes: bool) -> None:
    """Drop and recreate every table. Destructive."""
    if not yes:
        click.confirm("This deletes all data. Continue?", abort=True)
    db.drop_all()
    db.create_all()
    click.echo("Database reset.")


@click.command("create-user")
@click.option("--username", prompt=True)
@click.option("--full-name", prompt="Full name")
@click.option(
    "--role",
    type=click.Choice([role.value for role in Role]),
    default=Role.ADMIN.value,
    prompt=True,
)
@click.option("--email", default=None)
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
@with_appcontext
def create_user_command(username, full_name, role, email, password) -> None:
    """Create a login without leaving the terminal."""
    school = get_school()
    if school is None:
        raise click.ClickException("Run the web setup first (or seed-demo) to create the school.")
    if User.query.filter(func.lower(User.username) == username.lower()).first():
        raise click.ClickException("That username is already taken.")
    user = bootstrap.create_user(
        school=school,
        username=username,
        password=password,
        full_name=full_name,
        role=Role(role),
        email=email,
    )
    db.session.commit()
    click.echo(f"Created {user.username} ({user.role.value}).")


@click.command("set-password")
@click.argument("username")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
@with_appcontext
def set_password_command(username, password) -> None:
    """Reset a user's password directly (recovery access)."""
    user = User.query.filter(func.lower(User.username) == username.lower()).first()
    if user is None:
        raise click.ClickException("No such user.")
    user.set_password(password)
    user.is_active = True
    user.locked_until = None
    user.must_change_password = False
    db.session.commit()
    click.echo(f"Password updated for {user.username}.")


@click.command("backup")
@click.option("--note", default="manual", help="Suffix for the backup file.")
@with_appcontext
def backup_command(note: str) -> None:
    """Take a consistent SQLite backup using the online backup API."""
    database = db.engine.url.database
    if not database or database == ":memory:":
        raise click.ClickException("No file-backed database to back up.")
    source = Path(database)
    if not source.exists():
        raise click.ClickException(f"Database file not found: {source}")

    folder = Path(current_app.config["BACKUP_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = folder / f"school-{stamp}-{note}.db"

    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    click.echo(f"Backup written to {target}")


# --------------------------------------------------------------------------
# Demo data
# --------------------------------------------------------------------------
FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan",
    "Ishaan", "Rudra", "Ananya", "Diya", "Aadhya", "Saanvi", "Pari", "Anika",
    "Myra", "Ira", "Kiara", "Riya", "Kabir", "Dhruv", "Neha", "Meera", "Rohan",
    "Tara", "Nikhil", "Sara", "Yash", "Kavya", "Aryan", "Nisha", "Manav", "Pooja",
    "Dev", "Shreya", "Karan", "Aisha", "Rahul", "Sneha",
]
LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Reddy", "Nair", "Iyer", "Singh", "Gupta",
    "Mehta", "Joshi", "Kulkarni", "Desai", "Chopra", "Kapoor", "Bose", "Mishra",
]

SUBJECTS = [
    ("ENG", "English"),
    ("HIN", "Hindi"),
    ("MAT", "Mathematics"),
    ("SCI", "Science"),
    ("SST", "Social Science"),
    ("CSC", "Computer Science"),
]

TEACHERS = [
    ("Anita Deshpande", "Mathematics", "M.Sc, B.Ed"),
    ("Rajesh Iyer", "English", "M.A, B.Ed"),
    ("Sunita Verma", "Science", "M.Sc, B.Ed"),
    ("Prakash Nair", "Social Science", "M.A, B.Ed"),
    ("Farah Khan", "Hindi", "M.A, B.Ed"),
    ("Vikram Rao", "Computer Science", "MCA, B.Ed"),
]


@click.command("seed-demo")
@click.option("--force", is_flag=True, help="Wipe existing data and rebuild the demo school.")
@with_appcontext
def seed_demo(force: bool) -> None:
    """Build a complete, realistic demo school for evaluation."""
    existing = School.query.first()
    if existing is not None and not force:
        raise click.ClickException(
            "A school already exists. Use --force to replace all data with the demo school."
        )
    if existing is not None and force:
        if not click.confirm("This deletes all existing data. Continue?", abort=True):
            return
        db.drop_all()
        db.create_all()

    rng = random.Random(20261101)
    today = date.today()

    school = bootstrap.create_school(
        name="Sunrise Public School",
        short_name="Sunrise",
        address_line1="14 Nehru Road",
        city="Pune",
        state="Maharashtra",
        pincode="411001",
        phone="+91 20 2555 0180",
        email="office@sunriseschool.example",
        primary_color="#1D4E89",
        secondary_color="#B7791F",
        is_demo=True,
    )
    school.affiliation_no = "CBSE/1130/2019"
    school.principal_name = "Dr. Meera Kulkarni"
    school.motto = "Knowledge · Character · Service"
    academic_session = AcademicSession.query.filter_by(is_current=True).first()

    click.echo("Creating classes and subjects…")
    classes = []
    for level in range(6, 11):
        school_class = SchoolClass(
            school_id=school.id, level=level, name=f"Class {level}", display_order=level
        )
        db.session.add(school_class)
        db.session.flush()
        classes.append(school_class)

    subjects = []
    for order, (code, name) in enumerate(SUBJECTS):
        subject = Subject(
            school_id=school.id, code=code, name=name, display_order=order
        )
        db.session.add(subject)
        subjects.append(subject)
    db.session.flush()

    for school_class in classes:
        for subject in subjects:
            db.session.add(
                ClassSubject(
                    school_id=school.id,
                    session_id=academic_session.id,
                    school_class_id=school_class.id,
                    subject_id=subject.id,
                    default_max_marks=100,
                )
            )

    sections = []
    for school_class in classes:
        for name in ("A", "B"):
            section = Section(
                school_id=school.id,
                session_id=academic_session.id,
                school_class_id=school_class.id,
                name=name,
                room=f"{school_class.level}{name}",
                capacity=40,
            )
            db.session.add(section)
            sections.append(section)
    db.session.flush()

    click.echo("Creating staff accounts…")
    owner = bootstrap.create_user(
        school=school,
        username="admin",
        password="Admin@12345",
        full_name="Rohit Joshi",
        role=Role.SUPERUSER,
        email="admin@sunriseschool.example",
        phone="+91 98220 11001",
    )
    principal = bootstrap.create_user(
        school=school,
        username="principal",
        password="Principal@12345",
        full_name="Dr. Meera Kulkarni",
        role=Role.PRINCIPAL,
        email="principal@sunriseschool.example",
    )
    accounts = bootstrap.create_user(
        school=school,
        username="accounts",
        password="Accounts@12345",
        full_name="Suresh Pawar",
        role=Role.ACCOUNTS,
    )

    teacher_profiles = []
    for index, (name, specialisation, qualification) in enumerate(TEACHERS):
        username = f"teacher{index + 1}"
        user = bootstrap.create_user(
            school=school,
            username=username,
            password="Teacher@12345",
            full_name=name,
            role=Role.TEACHER,
            email=f"{username}@sunriseschool.example",
        )
        profile = StaffProfile(
            school_id=school.id,
            user_id=user.id,
            employee_code=f"EMP{index + 1:03d}",
            staff_type=StaffType.TEACHING,
            designation="Senior Teacher" if index < 2 else "Teacher",
            department=specialisation,
            qualification=qualification,
            specialisation=specialisation,
            joining_date=date(today.year - 3 - index // 2, 6, 1),
            employment_type="FULL_TIME",
            employment_status="ACTIVE",
            gender=Gender.FEMALE if index in (0, 2, 4) else Gender.MALE,
            phone=f"+91 98220 2{index:04d}",
        )
        db.session.add(profile)
        teacher_profiles.append((profile, specialisation))
    db.session.flush()

    db.session.add(
        StaffProfile(
            school_id=school.id,
            user_id=accounts.id,
            employee_code="EMP100",
            staff_type=StaffType.ACCOUNTS,
            designation="Accounts Officer",
            department="Finance",
            joining_date=date(today.year - 4, 4, 1),
            employment_status="ACTIVE",
        )
    )

    click.echo("Assigning subjects and class teachers…")
    for index, school_class in enumerate(classes):
        for section in [s for s in sections if s.school_class_id == school_class.id]:
            section.class_teacher_id = teacher_profiles[index % len(teacher_profiles)][0].id

    for section in sections:
        for subject in subjects:
            match = next(
                (
                    profile
                    for profile, specialisation in teacher_profiles
                    if specialisation == subject.name
                ),
                teacher_profiles[0][0],
            )
            db.session.add(
                SubjectAllocation(
                    school_id=school.id,
                    session_id=academic_session.id,
                    section_id=section.id,
                    subject_id=subject.id,
                    teacher_id=match.id,
                    periods_per_week=5,
                )
            )
    db.session.flush()

    click.echo("Admitting students…")
    demo_students: list[Student] = []
    for section in sections:
        for slot in range(1, 7):
            first = FIRST_NAMES[(section.id * 7 + slot) % len(FIRST_NAMES)]
            last = LAST_NAMES[(section.id * 3 + slot) % len(LAST_NAMES)]
            student = student_service.create_student(
                school_id=school.id,
                session=academic_session,
                first_name=first,
                last_name=last,
                section=section,
                dob=date(today.year - (section.school_class.level + 6), ((slot * 3) % 12) + 1, ((slot * 7) % 27) + 1),
                gender=Gender.FEMALE if slot % 2 else Gender.MALE,
                roll_no=slot,
                phone=f"+91 90000 {section.id:02d}{slot:03d}",
                city="Pune",
                state="Maharashtra",
                emergency_name=f"{first}'s parent",
                emergency_phone=f"+91 90000 {section.id:02d}{slot:03d}",
            )
            demo_students.append(student)
    db.session.flush()

    click.echo("Creating guardians…")
    demo_parent = bootstrap.create_user(
        school=school,
        username="parent",
        password="Parent@12345",
        full_name="Sanjay Kulkarni",
        role=Role.PARENT,
        email="parent@example.com",
        phone="+91 98220 44556",
    )
    guardian = Guardian(
        school_id=school.id,
        user_id=demo_parent.id,
        full_name="Sanjay Kulkarni",
        occupation="Architect",
        phone="+91 98220 44556",
        email="parent@example.com",
        address="7 Lake View Society, Pune",
        is_verified=True,
    )
    db.session.add(guardian)
    db.session.flush()

    for student in demo_students[:2]:
        db.session.add(
            GuardianStudentLink(
                school_id=school.id,
                guardian_id=guardian.id,
                student_id=student.id,
                relationship="Father",
                is_primary=True,
                status=LinkStatus.VERIFIED,
                verified_by_id=owner.id,
                verified_at=datetime.utcnow(),
            )
        )
    for student in demo_students[2:20]:
        guardian_row = Guardian(
            school_id=school.id,
            full_name=f"{student.last_name} household",
            phone=f"+91 90000 {student.id:05d}",
            is_verified=True,
        )
        db.session.add(guardian_row)
        db.session.flush()
        db.session.add(
            GuardianStudentLink(
                school_id=school.id,
                guardian_id=guardian_row.id,
                student_id=student.id,
                relationship="Mother",
                is_primary=True,
                status=LinkStatus.VERIFIED,
                verified_by_id=owner.id,
                verified_at=datetime.utcnow(),
            )
        )
    db.session.flush()

    click.echo("Creating the student demo login…")
    demo_student_user = bootstrap.create_user(
        school=school,
        username="student",
        password="Student@12345",
        full_name=demo_students[0].full_name,
        role=Role.STUDENT,
    )
    demo_students[0].user_id = demo_student_user.id

    click.echo("Building the timetable…")
    timetable = Timetable(
        school_id=school.id,
        session_id=academic_session.id,
        name="Master Timetable",
        status=TimetableStatus.PUBLISHED,
    )
    db.session.add(timetable)
    db.session.flush()
    default_periods = [
        ("P1", time(8, 0), time(8, 45)),
        ("P2", time(8, 45), time(9, 30)),
        ("Break", time(9, 30), time(9, 45)),
        ("P3", time(9, 45), time(10, 30)),
        ("P4", time(10, 30), time(11, 15)),
        ("Lunch", time(11, 15), time(11, 45)),
        ("P5", time(11, 45), time(12, 30)),
        ("P6", time(12, 30), time(13, 15)),
        ("P7", time(13, 15), time(14, 0)),
    ]
    periods = []
    for sequence, (label, start, end) in enumerate(default_periods, start=1):
        kind = (
            PeriodKind.BREAK
            if label == "Break"
            else PeriodKind.LUNCH
            if label == "Lunch"
            else PeriodKind.CLASS
        )
        period = TimetablePeriod(
            school_id=school.id,
            timetable_id=timetable.id,
            sequence=sequence,
            label=label,
            start_time=start,
            end_time=end,
            kind=kind,
        )
        db.session.add(period)
        periods.append(period)
    db.session.flush()

    teaching_periods = [p for p in periods if p.kind.value == "CLASS"]
    busy: set[tuple[int, int, int]] = set()
    allocation_map = {
        (row.section_id, row.subject_id): row.teacher_id
        for row in SubjectAllocation.query.filter_by(session_id=academic_session.id).all()
    }
    subject_index = 0
    for section in sections:
        for weekday in range(6):
            for period in teaching_periods:
                if weekday == 5 and period.sequence > 7:
                    continue
                subject = subjects[subject_index % len(subjects)]
                subject_index += 1
                teacher_id = allocation_map.get((section.id, subject.id))
                if teacher_id and (teacher_id, weekday, period.id) in busy:
                    continue
                if teacher_id:
                    busy.add((teacher_id, weekday, period.id))
                db.session.add(
                    TimetableEntry(
                        school_id=school.id,
                        timetable_id=timetable.id,
                        section_id=section.id,
                        weekday=weekday,
                        period_id=period.id,
                        subject_id=subject.id,
                        teacher_id=teacher_id,
                        room=section.room,
                    )
                )
    db.session.flush()

    click.echo("Marking attendance for the last two weeks…")
    for offset in range(14, -1, -1):
        day = today - timedelta(days=offset)
        if day.weekday() == 6:
            continue
        for section in sections:
            enrollments = Enrollment.query.filter_by(
                section_id=section.id, status=EnrollmentStatus.ACTIVE
            ).all()
            for enrollment in enrollments:
                roll = rng.random()
                status = (
                    AttendanceStatus.ABSENT
                    if roll < 0.06
                    else AttendanceStatus.LATE
                    if roll < 0.10
                    else AttendanceStatus.PRESENT
                )
                db.session.add(
                    AttendanceRecord(
                        school_id=school.id,
                        student_id=enrollment.student_id,
                        enrollment_id=enrollment.id,
                        section_id=section.id,
                        date=day,
                        status=status,
                        marked_by_id=owner.id,
                        marked_at=datetime.utcnow(),
                    )
                )

    click.echo("Creating fee heads, structures and payments…")
    categories = []
    for code, name, frequency, amount in [
        ("TUI", "Tuition Fee", FeeFrequency.ANNUAL, 4800000),
        ("TRN", "Transport Fee", FeeFrequency.ANNUAL, 1200000),
        ("EXM", "Examination Fee", FeeFrequency.ANNUAL, 150000),
    ]:
        category = FeeCategory(
            school_id=school.id,
            session_id=academic_session.id,
            code=code,
            name=name,
            frequency=frequency,
            is_optional=code == "TRN",
            description=f"{name} for the academic year",
        )
        db.session.add(category)
        categories.append(category)
    db.session.flush()

    for school_class in classes:
        index = school_class.level - 6
        for category, base in zip(categories, [4600000 + index * 200000, 1200000, 150000]):
            db.session.add(
                FeeStructure(
                    school_id=school.id,
                    session_id=academic_session.id,
                    school_class_id=school_class.id,
                    fee_category_id=category.id,
                    installment_no=1,
                    amount_paise=base,
                    due_date=date(today.year, 7, 15),
                )
            )
    db.session.flush()

    for section in sections:
        fee_service.generate_for_section(academic_session.id, section.id, owner.id)

    rows = StudentFee.query.filter_by(session_id=academic_session.id).all()
    for index, row in enumerate(rows):
        if index % 5 == 0:
            continue
        pay_fraction = 1 if index % 3 else 0.5
        amount = int(row.net_paise * pay_fraction)
        if amount <= 0:
            continue
        fee_service.record_payment(
            student_fee=row,
            amount_paise=amount,
            method=PaymentMethod.UPI_OFFLINE if index % 2 else PaymentMethod.CASH,
            actor_id=accounts.id,
            reference=f"DEMO{index:04d}",
        )

    click.echo("Creating homework…")
    for section in sections[:6]:
        for subject in subjects[:2]:
            assignment = SubjectAllocation.query.filter_by(
                section_id=section.id, subject_id=subject.id
            ).first()
            db.session.add(
                Homework(
                    school_id=school.id,
                    session_id=academic_session.id,
                    section_id=section.id,
                    subject_id=subject.id,
                    teacher_id=assignment.teacher_id if assignment else None,
                    title=f"{subject.name}: worksheet {section.label}",
                    description="Complete the worksheet in your notebook and submit in class.",
                    assigned_on=today - timedelta(days=2),
                    due_at=datetime.combine(today + timedelta(days=3), time(9, 0)),
                    status=HomeworkStatus.PUBLISHED,
                    max_marks=10,
                )
            )

    click.echo("Running an examination end-to-end…")
    fa1 = ExamType.query.filter_by(code="FA1").first()
    grading_scale = GradeScale.query.filter_by(is_default=True).first()
    exam = Examination(
        school_id=school.id,
        session_id=academic_session.id,
        exam_type_id=fa1.id,
        name="FA1 Unit Test",
        start_date=today - timedelta(days=21),
        end_date=today - timedelta(days=16),
        result_date=today - timedelta(days=10),
        status=ExamStatus.MARKS_ENTRY,
        grading_scale_id=grading_scale.id if grading_scale else None,
        created_by_id=owner.id,
        instructions="Bring your own stationery. Calculators are not permitted.",
    )
    db.session.add(exam)
    db.session.flush()
    for school_class in classes:
        db.session.add(
            ExaminationClass(
                school_id=school.id,
                examination_id=exam.id,
                school_class_id=school_class.id,
            )
        )
        for subject in subjects:
            db.session.add(
                ExaminationSubject(
                    school_id=school.id,
                    examination_id=exam.id,
                    school_class_id=school_class.id,
                    subject_id=subject.id,
                    exam_date=today - timedelta(days=20),
                    start_time=time(9, 0),
                    end_time=time(10, 30),
                    max_marks=25,
                    pass_marks=9,
                )
            )
    db.session.flush()
    ensure_sheets(exam)

    sheets = MarksEntrySheet.query.join(MarksEntrySheet.exam_subject).filter(
        ExaminationSubject.examination_id == exam.id
    ).all()
    for sheet in sheets:
        for enrollment in Enrollment.query.filter_by(
            section_id=sheet.section_id, status=EnrollmentStatus.ACTIVE
        ).all():
            db.session.add(
                MarksRecord(
                    school_id=school.id,
                    sheet_id=sheet.id,
                    student_id=enrollment.student_id,
                    enrollment_id=enrollment.id,
                    marks_obtained=rng.randint(9, 25),
                    status=MarkStatus.PRESENT,
                    updated_by_id=sheet.teacher.user_id if sheet.teacher else owner.id,
                )
            )
        sheet.status = SheetStatus.APPROVED
        sheet.approved_by_id = principal.id
        sheet.approved_at = datetime.utcnow()
        sheet.submitted_at = datetime.utcnow()
    db.session.commit()

    stats = compute_results(exam, principal.id)
    publish(exam, principal.id)
    click.echo(f"  {stats['computed']} results computed and published.")

    click.echo("Generating a few report cards…")
    sample = ResultSummary.query.filter_by(examination_id=exam.id).limit(8).all()
    for result in sample:
        try:
            generate_report_card(exam, result.student, principal.id)
        except Exception as error:  # pragma: no cover - demo resilience
            click.echo(f"  skipped report card: {error}")
    db.session.commit()

    click.echo("Publishing announcements…")
    for title, body, category, scope in [
        (
            "Parent–Teacher Meeting",
            "The parent–teacher meeting for all classes will be held on Saturday "
            "from 9:00 am to 12:30 pm in the respective classrooms.",
            AnnouncementCategory.GENERAL,
            AnnouncementScope.ALL,
        ),
        (
            "FA1 results published",
            "FA1 unit test results are now available in the parent and student portals.",
            AnnouncementCategory.EXAM,
            AnnouncementScope.ALL,
        ),
        (
            "Staff meeting",
            "A short staff meeting will be held in the staff room at 3:30 pm today.",
            AnnouncementCategory.GENERAL,
            AnnouncementScope.STAFF,
        ),
    ]:
        announcement = Announcement(
            school_id=school.id,
            session_id=academic_session.id,
            author_id=owner.id,
            title=title,
            body=body,
            category=category,
            audience_scope=scope,
            status=AnnouncementStatus.PUBLISHED,
            publish_at=datetime.utcnow() - timedelta(hours=2),
            is_pinned=category == AnnouncementCategory.GENERAL,
        )
        db.session.add(announcement)
    db.session.commit()

    click.echo("")
    click.echo("Demo school ready. Sign in at http://127.0.0.1:5000/login")
    click.echo("  Owner      admin      / Admin@12345")
    click.echo("  Principal  principal  / Principal@12345")
    click.echo("  Accounts   accounts   / Accounts@12345")
    click.echo("  Teacher    teacher1   / Teacher@12345")
    click.echo("  Parent     parent     / Parent@12345   (2 children)")
    click.echo("  Student    student    / Student@12345")
