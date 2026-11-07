"""Student portal.

The signed-in student can only ever read their own records; the student row is
resolved from the session, never from a URL parameter.
"""
from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..models import (
    Examination,
    ExaminationClass,
    Homework,
    HomeworkSubmission,
    ReportCard,
    ResultSummary,
    StudyMaterial,
)
from ..models.base import utcnow
from ..models.enums import (
    ExamStatus,
    ReportCardStatus,
    SubmissionStatus,
)
from ..services import attendance as attendance_service
from ..services.communication import visible_announcements
from ..services.dashboard import student_overview
from ..services.exams import latest_report_card, subject_breakdown
from ..services.settings import current_session
from ..services.timetable import published_timetable, section_week
from ..utils.uploads import UploadError, save_upload

bp = Blueprint("student", __name__, url_prefix="/student")


@bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.student_login", next=request.full_path))
    if current_user.role.value != "STUDENT":
        abort(403)
    if current_user.student is None:
        abort(403)


def _me():
    student = current_user.student
    if student is None:
        abort(403)
    return student


@bp.get("/")
def home():
    student = _me()
    session = current_session()
    data = student_overview(student, session.id) if session else {"empty": True}
    return render_template("student/home.html", student=student, data=data)


@bp.get("/timetable")
def timetable():
    student = _me()
    session = current_session()
    enrollment = student.enrollment_for(session.id) if session else None
    table = published_timetable(session.id) if session else None
    week = section_week(table, enrollment.section_id) if table and enrollment else {}
    return render_template(
        "student/timetable.html",
        student=student,
        enrollment=enrollment,
        timetable=table,
        week=week,
        periods=table.periods if table else [],
        days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    )


@bp.get("/attendance")
def attendance():
    student = _me()
    session = current_session()
    summary = attendance_service.student_summary(student.id, session.id if session else None)
    return render_template(
        "student/attendance.html", student=student, summary=summary, rows=summary["rows"][:90]
    )


@bp.get("/homework")
def homework():
    student = _me()
    session = current_session()
    enrollment = student.enrollment_for(session.id) if session else None
    rows = []
    if enrollment:
        submissions = {
            row.homework_id: row
            for row in HomeworkSubmission.query.filter_by(student_id=student.id).all()
        }
        for item in (
            Homework.query.filter_by(section_id=enrollment.section_id)
            .order_by(Homework.assigned_on.desc())
            .all()
        ):
            rows.append({"homework": item, "submission": submissions.get(item.id)})
    return render_template("student/homework.html", student=student, rows=rows)


@bp.post("/homework/<int:homework_id>/submit")
def submit_homework(homework_id: int):
    student = _me()
    session = current_session()
    item = db.get_or_404(Homework, homework_id)
    enrollment = student.enrollment_for(session.id) if session else None
    if enrollment is None or item.section_id != enrollment.section_id:
        abort(404)

    submission = HomeworkSubmission.query.filter_by(
        homework_id=item.id, student_id=student.id
    ).first()
    if submission is None:
        submission = HomeworkSubmission(
            school_id=item.school_id, homework_id=item.id, student_id=student.id
        )
        db.session.add(submission)

    if submission.status in (SubmissionStatus.REVIEWED, SubmissionStatus.RETURNED):
        flash("This submission has already been reviewed.", "warning")
        return redirect(url_for("student.homework"))

    file_id = submission.file_id
    if request.form.get("remove_file") and file_id:
        file_id = None
    upload = request.files.get("file")
    if upload and upload.filename:
        try:
            file_id = save_upload(upload, "submissions", current_user.id).id
        except UploadError as error:
            flash(str(error), "error")
            return redirect(url_for("student.homework"))

    submission.file_id = file_id
    submission.submitted_at = utcnow()
    submission.status = SubmissionStatus.LATE if item.is_overdue else SubmissionStatus.SUBMITTED
    if request.form.get("note"):
        submission.remarks = request.form.get("note", "")[:500]
    db.session.commit()
    flash("Homework submitted.", "success")
    return redirect(url_for("student.homework"))


@bp.get("/materials")
def materials():
    student = _me()
    session = current_session()
    enrollment = student.enrollment_for(session.id) if session else None
    rows = []
    if session and enrollment:
        rows = (
            StudyMaterial.query.filter_by(
                session_id=session.id,
                school_class_id=enrollment.section.school_class_id,
                is_published=True,
            )
            .order_by(StudyMaterial.created_at.desc())
            .all()
        )
        rows = [
            row
            for row in rows
            if row.section_id is None or row.section_id == enrollment.section_id
        ]
    return render_template(
        "student/materials.html", student=student, rows=rows, enrollment=enrollment
    )


@bp.get("/exams")
def exams():
    student = _me()
    session = current_session()
    rows = []
    if session:
        enrollment = student.enrollment_for(session.id)
        if enrollment:
            rows = (
                Examination.query.join(
                    ExaminationClass, ExaminationClass.examination_id == Examination.id
                )
                .filter(
                    Examination.session_id == session.id,
                    ExaminationClass.school_class_id == enrollment.section.school_class_id,
                )
                .order_by(Examination.start_date.desc(), Examination.id.desc())
                .all()
            )
    return render_template("student/exams.html", student=student, rows=rows)


@bp.get("/results")
def results():
    student = _me()
    session = current_session()
    published = (
        Examination.query.filter_by(session_id=session.id, status=ExamStatus.PUBLISHED)
        .order_by(Examination.result_date.desc(), Examination.id.desc())
        .all()
        if session
        else []
    )
    rows = []
    for exam in published:
        summary = ResultSummary.query.filter_by(
            examination_id=exam.id, student_id=student.id
        ).first()
        if summary is None:
            continue
        rows.append(
            {"exam": exam, "summary": summary, "subjects": subject_breakdown(exam, student)}
        )
    return render_template("student/results.html", student=student, rows=rows)


@bp.get("/report-cards")
def report_cards():
    student = _me()
    session = current_session()
    exams = (
        Examination.query.filter_by(session_id=session.id, status=ExamStatus.PUBLISHED)
        .order_by(Examination.result_date.desc(), Examination.id.desc())
        .all()
        if session
        else []
    )
    cards = []
    for exam in exams:
        card = latest_report_card(exam.id, student.id)
        if card and card.status != ReportCardStatus.DRAFT:
            cards.append({"exam": exam, "card": card})
    return render_template("student/report_cards.html", student=student, cards=cards)


@bp.get("/report-cards/<int:card_id>.pdf")
def report_card_pdf(card_id: int):
    student = _me()
    card = db.get_or_404(ReportCard, card_id)
    if card.student_id != student.id or card.status == ReportCardStatus.DRAFT:
        abort(404)
    return redirect(url_for("files.serve", file_uuid=card.pdf_file.uuid))


@bp.get("/announcements")
def announcements():
    session = current_session()
    rows = (
        visible_announcements(current_user, session.id).limit(50).all() if session else []
    )
    return render_template("student/announcements.html", rows=rows)


@bp.get("/profile")
def profile():
    student = _me()
    session = current_session()
    enrollment = student.enrollment_for(session.id) if session else None
    return render_template(
        "student/profile.html", student=student, enrollment=enrollment
    )
