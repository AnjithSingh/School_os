"""Student admission, promotion, transfer and search."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_

from ..extensions import db
from ..models import (
    AcademicSession,
    Enrollment,
    Guardian,
    GuardianStudentLink,
    SchoolClass,
    Section,
    Student,
    User,
)
from ..models.enums import (
    EnrollmentStatus,
    Gender,
    LinkStatus,
    Role,
    StudentStatus,
)
from ..models.base import utcnow
from .audit import record


def next_admission_no(school_id: int) -> str:
    prefix = f"ADM{date.today().year}"
    rows = (
        db.session.query(Student.admission_no)
        .filter(Student.school_id == school_id, Student.admission_no.like(f"{prefix}%"))
        .all()
    )
    highest = 0
    for (value,) in rows:
        tail = value.replace(prefix, "")
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f"{prefix}{highest + 1:04d}"


def find_section(session_id: int, class_id: int, section_id: int | None = None) -> Section | None:
    if section_id:
        return Section.query.filter_by(id=section_id, session_id=session_id, is_active=True).first()
    return (
        Section.query.filter_by(session_id=session_id, school_class_id=class_id, is_active=True)
        .order_by(Section.name)
        .first()
    )


def create_student(
    *,
    school_id: int,
    session: AcademicSession,
    first_name: str,
    last_name: str,
    section: Section,
    dob: date | None = None,
    gender: Gender | None = None,
    admission_no: str | None = None,
    admission_date: date | None = None,
    roll_no: int | None = None,
    photo_file_id: int | None = None,
    address: str | None = None,
    city: str | None = None,
    state: str | None = None,
    pincode: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    emergency_name: str | None = None,
    emergency_phone: str | None = None,
    category: str | None = None,
    previous_school: str | None = None,
    previous_class: str | None = None,
    notes: str | None = None,
    actor_id: int | None = None,
) -> Student:
    student = Student(
        school_id=school_id,
        admission_no=(admission_no or "").strip() or next_admission_no(school_id),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        dob=dob,
        gender=gender,
        photo_file_id=photo_file_id,
        address=address,
        city=city,
        state=state,
        pincode=pincode,
        phone=phone,
        email=email,
        emergency_name=emergency_name,
        emergency_phone=emergency_phone,
        category=category,
        admission_date=admission_date or date.today(),
        notes=notes,
        status=StudentStatus.ACTIVE,
    )
    db.session.add(student)
    db.session.flush()

    enrollment = Enrollment(
        school_id=school_id,
        student_id=student.id,
        session_id=session.id,
        section_id=section.id,
        roll_no=roll_no,
        status=EnrollmentStatus.ACTIVE,
        admitted_on=student.admission_date,
        previous_school=previous_school,
        previous_class=previous_class,
    )
    db.session.add(enrollment)
    record(
        "student.admitted",
        "Student",
        student.id,
        summary=f"{student.full_name} admitted to {section.label}",
        after={"admission_no": student.admission_no, "section": section.label},
        actor_id=actor_id,
    )
    return student


def create_guardian(
    *,
    school_id: int,
    full_name: str,
    relationship: str = "Guardian",
    student: Student | None = None,
    phone: str | None = None,
    email: str | None = None,
    occupation: str | None = None,
    address: str | None = None,
    username: str | None = None,
    password: str | None = None,
    actor_id: int | None = None,
    verify: bool = True,
    permissions: dict | None = None,
) -> Guardian:
    user = None
    if username and password:
        user = User(
            school_id=school_id,
            username=username.strip().lower(),
            email=(email.lower() if email else None),
            full_name=full_name.strip(),
            role=Role.PARENT,
            phone=phone,
            must_change_password=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

    guardian = Guardian(
        school_id=school_id,
        user_id=user.id if user else None,
        full_name=full_name.strip(),
        phone=phone,
        email=email,
        occupation=occupation,
        address=address,
        is_verified=verify,
    )
    db.session.add(guardian)
    db.session.flush()

    if student is not None:
        link_guardian(
            guardian=guardian,
            student=student,
            relationship=relationship,
            actor_id=actor_id,
            verify=verify,
            permissions=permissions or {},
        )
    record("guardian.created", "Guardian", guardian.id, summary=guardian.full_name, actor_id=actor_id)
    return guardian


def link_guardian(
    *,
    guardian: Guardian,
    student: Student,
    relationship: str = "Guardian",
    actor_id: int | None = None,
    verify: bool = False,
    is_primary: bool = False,
    permissions: dict | None = None,
) -> GuardianStudentLink:
    permissions = permissions or {}
    link = GuardianStudentLink.query.filter_by(
        guardian_id=guardian.id, student_id=student.id
    ).first()
    if link is None:
        link = GuardianStudentLink(
            school_id=guardian.school_id,
            guardian_id=guardian.id,
            student_id=student.id,
        )
        db.session.add(link)

    link.relationship = relationship
    link.is_primary = is_primary
    link.can_view_academics = permissions.get("academics", True)
    link.can_view_attendance = permissions.get("attendance", True)
    link.can_pay_fees = permissions.get("fees", True)
    link.can_apply_leave = permissions.get("leave", True)
    link.can_view_homework = permissions.get("homework", True)
    link.receive_notifications = permissions.get("notifications", True)
    link.created_by_id = link.created_by_id or actor_id
    if verify:
        link.status = LinkStatus.VERIFIED
        link.verified_by_id = actor_id
        link.verified_at = utcnow()
    record(
        "guardian.linked",
        "GuardianStudentLink",
        link.id,
        summary=f"{guardian.full_name} → {student.full_name}",
        actor_id=actor_id,
    )
    return link


def verify_link(link: GuardianStudentLink, actor_id: int) -> GuardianStudentLink:
    link.status = LinkStatus.VERIFIED
    link.verified_by_id = actor_id
    link.verified_at = utcnow()
    record("guardian.verified", "GuardianStudentLink", link.id, actor_id=actor_id)
    return link


def revoke_link(link: GuardianStudentLink, actor_id: int) -> None:
    link.status = LinkStatus.REVOKED
    record("guardian.revoked", "GuardianStudentLink", link.id, actor_id=actor_id)


def list_students(
    *,
    q: str | None = None,
    session_id: int | None = None,
    class_id: int | None = None,
    section_id: int | None = None,
    status: StudentStatus | None = None,
):
    query = Student.query.filter(Student.deleted_at.is_(None))
    if q:
        needle = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(Student.first_name + " " + Student.last_name).like(needle),
                func.lower(Student.admission_no).like(needle),
                func.lower(func.coalesce(Student.phone, "")).like(needle),
            )
        )
    if session_id:
        query = query.join(Enrollment, Enrollment.student_id == Student.id).filter(
            Enrollment.session_id == session_id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )
        if class_id or section_id:
            if section_id:
                query = query.filter(Enrollment.section_id == section_id)
            else:
                query = query.join(Section, Section.id == Enrollment.section_id).filter(
                    Section.school_class_id == class_id
                )
    if status:
        query = query.filter(Student.status == status)
    return query.order_by(Student.first_name, Student.last_name)


def promote_preview(from_session: AcademicSession, to_session: AcademicSession) -> list[dict]:
    """Dry run. Nothing is written; the caller shows this table for confirmation."""
    target_sections = Section.query.filter_by(session_id=to_session.id, is_active=True).all()
    classes = {c.id: c for c in SchoolClass.query.all()}
    rows: list[dict] = []

    enrollments = (
        Enrollment.query.filter_by(session_id=from_session.id, status=EnrollmentStatus.ACTIVE)
        .join(Enrollment.student)
        .order_by(Section.name, Enrollment.roll_no)
        .all()
    )
    for enrollment in enrollments:
        student = enrollment.student
        current_class = classes.get(enrollment.section.school_class_id) if enrollment.section else None
        target_class = None
        if current_class:
            target_class = next((c for c in classes.values() if c.level == current_class.level + 1), None)

        existing = Enrollment.query.filter_by(
            student_id=student.id, session_id=to_session.id
        ).first()

        target_section = None
        note = ""
        if existing:
            note = f"Already enrolled in {existing.section.label} for {to_session.name}"
        elif target_class is None:
            note = "Final year — mark as alumni"
        else:
            same_name = next(
                (
                    s
                    for s in target_sections
                    if s.school_class_id == target_class.id
                    and enrollment.section
                    and s.name == enrollment.section.name
                ),
                None,
            )
            target_section = same_name or next(
                (s for s in target_sections if s.school_class_id == target_class.id), None
            )
            if target_section is None:
                note = f"No section exists for {target_class.name} in {to_session.name}"

        rows.append(
            {
                "student": student,
                "from_section": enrollment.section,
                "to_section": target_section,
                "to_class": target_class,
                "graduating": target_class is None and not existing,
                "already": bool(existing),
                "note": note,
                "enrollment": enrollment,
            }
        )
    return rows


def promote_commit(
    from_session: AcademicSession,
    to_session: AcademicSession,
    actor_id: int | None = None,
) -> dict:
    rows = promote_preview(from_session, to_session)
    promoted = graduated = skipped = 0
    counters: dict[int, int] = {}

    for row in rows:
        if row["already"]:
            skipped += 1
            continue
        enrollment = row["enrollment"]
        if row["graduating"]:
            enrollment.status = EnrollmentStatus.PROMOTED
            enrollment.student.status = StudentStatus.ALUMNI
            graduated += 1
            continue
        target = row["to_section"]
        if target is None:
            skipped += 1
            continue
        next_no = counters.get(target.id)
        if next_no is None:
            from .academics import next_roll_no

            next_no = next_roll_no(target.id)
        counters[target.id] = next_no + 1
        db.session.add(
            Enrollment(
                school_id=enrollment.school_id,
                student_id=enrollment.student_id,
                session_id=to_session.id,
                section_id=target.id,
                roll_no=next_no,
                status=EnrollmentStatus.ACTIVE,
                admitted_on=to_session.start_date,
            )
        )
        enrollment.status = EnrollmentStatus.PROMOTED
        promoted += 1

    record(
        "students.promoted",
        "AcademicSession",
        to_session.id,
        summary=f"{promoted} promoted, {graduated} graduated, {skipped} skipped",
        actor_id=actor_id,
    )
    db.session.commit()
    return {"promoted": promoted, "graduated": graduated, "skipped": skipped}


def transfer_student(student: Student, reason: str, actor_id: int | None = None) -> None:
    enrollment = student.current_enrollment
    if enrollment:
        enrollment.status = EnrollmentStatus.TRANSFERRED
    student.status = StudentStatus.TRANSFERRED
    record("student.transferred", "Student", student.id, summary=reason, actor_id=actor_id)
    db.session.commit()


def guardians_of(student: Student):
    return (
        GuardianStudentLink.query.filter_by(student_id=student.id)
        .join(GuardianStudentLink.guardian)
        .order_by(GuardianStudentLink.is_primary.desc())
        .all()
    )


def update_student(student: Student, data: dict) -> Student:
    for field in (
        "first_name",
        "last_name",
        "address",
        "city",
        "state",
        "pincode",
        "phone",
        "email",
        "emergency_name",
        "emergency_phone",
        "category",
        "blood_group",
    ):
        if field in data:
            setattr(student, field, data[field])
    if "dob" in data:
        student.dob = data["dob"]
    if "gender" in data:
        student.gender = data["gender"]
    if "status" in data:
        student.status = data["status"]
    return student
