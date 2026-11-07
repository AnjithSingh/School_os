"""Dashboard data assembly for each role."""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import func

from ..extensions import db
from ..models import (
    Announcement,
    AttendanceRecord,
    Enrollment,
    Examination,
    FeePayment,
    GuardianStudentLink,
    Homework,
    HomeworkSubmission,
    MarksEntrySheet,
    ResultSummary,
    Section,
    StaffProfile,
    Student,
    StudentFee,
    SubjectAllocation,
)
from ..models.base import utcnow
from ..models.enums import (
    AnnouncementStatus,
    AttendanceStatus,
    EnrollmentStatus,
    ExamStatus,
    FeeStatus,
    HomeworkStatus,
    LinkStatus,
    ResultStatus,
    SheetStatus,
    StaffType,
    StudentStatus,
    SubmissionStatus,
)
from . import attendance as attendance_service
from . import fees as fee_service
from .communication import visible_announcements
from .settings import current_session


def admin_overview() -> dict:
    session = current_session()
    today = date.today()
    if session is None:
        return {"empty": True}

    total_students = (
        Student.query.filter(Student.status == StudentStatus.ACTIVE, Student.deleted_at.is_(None))
        .count()
    )
    total_teachers = (
        StaffProfile.query.filter_by(staff_type=StaffType.TEACHING).count()
    )
    total_staff = StaffProfile.query.count()
    total_sections = Section.query.filter_by(session_id=session.id, is_active=True).count()

    attendance = attendance_service.overview_for_date(today, session.id)
    absent_rows = (
        AttendanceRecord.query.filter_by(date=today, status=AttendanceStatus.ABSENT)
        .join(AttendanceRecord.student)
        .limit(8)
        .all()
    )

    upcoming = (
        Examination.query.filter(
            Examination.session_id == session.id,
            Examination.status.notin_([ExamStatus.ARCHIVED, ExamStatus.PUBLISHED]),
        )
        .order_by(Examination.start_date.is_(None), Examination.start_date)
        .limit(5)
        .all()
    )

    pending_marks = MarksEntrySheet.query.filter(
        MarksEntrySheet.status.in_([SheetStatus.DRAFT, SheetStatus.REOPENED])
    ).count()

    finance = fee_service.collection_summary(session.id)

    recent_admissions = (
        Enrollment.query.filter_by(session_id=session.id)
        .order_by(Enrollment.created_at.desc())
        .limit(5)
        .all()
    )

    announcements = (
        Announcement.query.filter_by(session_id=session.id, status=AnnouncementStatus.PUBLISHED)
        .order_by(Announcement.publish_at.desc())
        .limit(4)
        .all()
    )

    unverified_links = GuardianStudentLink.query.filter_by(status=LinkStatus.PENDING).count()
    overdue = StudentFee.query.filter(
        StudentFee.session_id == session.id,
        StudentFee.due_date < today,
        StudentFee.status.in_([FeeStatus.PENDING, FeeStatus.PARTIAL]),
    ).count()

    classes = (
        db.session.query(Section.school_class_id, func.count(Section.id))
        .filter_by(session_id=session.id, is_active=True)
        .group_by(Section.school_class_id)
        .all()
    )

    return {
        "empty": False,
        "session": session,
        "total_students": total_students,
        "total_teachers": total_teachers,
        "total_staff": total_staff,
        "total_sections": total_sections,
        "attendance": attendance,
        "absent_rows": absent_rows,
        "upcoming": upcoming,
        "pending_marks": pending_marks,
        "finance": finance,
        "recent_admissions": recent_admissions,
        "announcements": announcements,
        "unverified_links": unverified_links,
        "overdue_fees": overdue,
        "today": today,
    }


def teacher_overview(staff: StaffProfile) -> dict:
    from .timetable import day_entries, published_timetable

    session = current_session()
    today = date.today()
    timetable = published_timetable(session.id) if session else None

    allocations = (
        SubjectAllocation.query.filter_by(teacher_id=staff.id).all() if session else []
    )
    section_ids = {a.section_id for a in allocations}
    my_sections = (
        Section.query.filter(Section.id.in_(section_ids)).all() if section_ids else []
    )

    today_schedule = []
    if timetable:
        entries = []
        for section_id in section_ids:
            for item in day_entries(timetable, section_id, today):
                if item["entry"] and item["entry"].teacher_id == staff.id:
                    entries.append({"section": item["entry"].section, **item})
        entries.sort(key=lambda e: e["period"].start_time)
        today_schedule = entries

    unmarked = []
    for section in my_sections:
        marked = AttendanceRecord.query.filter_by(section_id=section.id, date=today).count()
        if marked == 0:
            unmarked.append(section)

    homework_due = (
        HomeworkSubmission.query.join(HomeworkSubmission.homework)
        .filter(
            Homework.teacher_id == staff.id,
            HomeworkSubmission.status == SubmissionStatus.SUBMITTED,
        )
        .count()
    )

    sheets = MarksEntrySheet.query.filter_by(teacher_id=staff.id).filter(
        MarksEntrySheet.status.in_([SheetStatus.DRAFT, SheetStatus.REOPENED])
    ).count()

    announcements = visible_announcements(staff.user, session.id).limit(4).all() if session else []

    return {
        "staff": staff,
        "session": session,
        "today": today,
        "timetable": timetable,
        "my_sections": my_sections,
        "today_schedule": today_schedule,
        "unmarked": unmarked,
        "homework_due": homework_due,
        "pending_sheets": sheets,
        "announcements": announcements,
    }


def child_overview(student: Student, session_id: int) -> dict:
    from .exams import build_snapshot
    from .timetable import day_entries, published_timetable

    today = date.today()
    timetable = published_timetable(session_id)
    enrollment = student.enrollment_for(session_id)
    schedule = day_entries(timetable, enrollment.section_id, today) if timetable and enrollment else []

    attendance = attendance_service.student_summary(student.id, session_id)
    ledger = fee_service.student_ledger(student.id, session_id)

    latest_results = (
        ResultSummary.query.filter_by(student_id=student.id)
        .join(ResultSummary.examination)
        .filter(Examination.session_id == session_id, Examination.status == ExamStatus.PUBLISHED)
        .order_by(Examination.start_date.desc())
        .limit(3)
        .all()
    )

    pending_homework = 0
    if enrollment:
        homework_ids = {
            h.id for h in Homework.query.filter_by(
                section_id=enrollment.section_id, status=HomeworkStatus.PUBLISHED
            ).all()
        }
        submitted = {
            s.homework_id
            for s in HomeworkSubmission.query.filter_by(student_id=student.id).all()
        }
        pending_homework = len(homework_ids - submitted)

    announcements = (
        Announcement.query.filter_by(session_id=session_id, status=AnnouncementStatus.PUBLISHED)
        .order_by(Announcement.publish_at.desc())
        .limit(3)
        .all()
    )

    return {
        "student": student,
        "enrollment": enrollment,
        "schedule": schedule,
        "attendance": attendance,
        "ledger": ledger,
        "latest_results": latest_results,
        "pending_homework": pending_homework,
        "announcements": announcements,
        "today": today,
    }


def student_overview(student: Student, session_id: int) -> dict:
    data = child_overview(student, session_id)
    data["upcoming_exams"] = (
        Examination.query.filter(
            Examination.session_id == session_id,
            Examination.start_date >= date.today(),
            Examination.status != ExamStatus.ARCHIVED,
        )
        .order_by(Examination.start_date)
        .limit(3)
        .all()
    )
    return data


def school_totals(session_id: int) -> dict:
    return {
        "students": Student.query.filter(
            Student.status == StudentStatus.ACTIVE, Student.deleted_at.is_(None)
        ).count(),
        "teachers": StaffProfile.query.filter_by(staff_type=StaffType.TEACHING).count(),
        "classes": Section.query.filter_by(session_id=session_id, is_active=True)
        .with_entities(Section.school_class_id)
        .distinct()
        .count(),
        "sections": Section.query.filter_by(session_id=session_id, is_active=True).count(),
    }
