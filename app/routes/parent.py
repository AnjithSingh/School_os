"""Parent / guardian portal.

Child context always travels in the URL. The signed-in guardian's verified
links are re-checked on every request, and each feature additionally checks the
per-link permission (academics, attendance, fees, homework, leave).
"""
from __future__ import annotations

from datetime import date

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session as flask_session,
    url_for,
)
from flask_login import current_user

from ..extensions import db
from ..forms.comms import LeaveForm
from ..models import (
    AcademicSession,
    Announcement,
    Enrollment,
    ExamRemark,
    Examination,
    ExaminationClass,
    GuardianStudentLink,
    Homework,
    HomeworkSubmission,
    LeaveApplication,
    ReportCard,
    ResultSummary,
    Section,
    Student,
    StudentFee,
    StudyMaterial,
)
from ..models.base import utcnow
from ..models.enums import (
    EnrollmentStatus,
    ExamStatus,
    FeeStatus,
    LeaveScope,
    LeaveStatus,
    LinkStatus,
    ReportCardStatus,
)
from ..security.scoping import verified_links
from ..services import attendance as attendance_service
from ..services import fees as fee_service
from ..services.communication import visible_announcements
from ..services.dashboard import child_overview
from ..services.exams import latest_report_card, subject_breakdown
from ..services.settings import current_session
from ..services.timetable import day_entries, published_timetable
from ..utils.money import to_paise
from ..utils.uploads import UploadError, save_upload

bp = Blueprint("parent", __name__, url_prefix="/parent")

PERMISSION_LABELS = {
    "academics": "results",
    "attendance": "attendance",
    "fees": "fees",
    "homework": "homework",
    "leave": "leave applications",
}


@bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.parent_login", next=request.full_path))
    if current_user.role.value != "PARENT":
        abort(403)
    if current_user.guardian is None:
        abort(403)


def _link_for(student_id: int) -> GuardianStudentLink:
    link = next(
        (row for row in verified_links() if row.student_id == student_id),
        None,
    )
    if link is None:
        abort(404)
    return link


def _child(student_id: int, permission: str = "profile") -> tuple[Student, GuardianStudentLink]:
    link = _link_for(student_id)
    attribute = {
        "academics": "can_view_academics",
        "attendance": "can_view_attendance",
        "fees": "can_pay_fees",
        "homework": "can_view_homework",
        "leave": "can_apply_leave",
        "profile": None,
    }[permission]
    if attribute and not getattr(link, attribute):
        flash(
            f"You do not have permission to view {PERMISSION_LABELS.get(permission, permission)} "
            "for this child. Ask the school office to update your access.",
            "error",
        )
        abort(403)
    return link.student, link


def _children() -> list[tuple[Student, GuardianStudentLink]]:
    return [(link.student, link) for link in verified_links() if link.student]


def _active_child(permission: str = "profile") -> Student | None:
    rows = _children()
    if not rows:
        return None
    wanted = flask_session.get("active_student_id")
    chosen = next((student for student, _ in rows if student.id == wanted), None)
    if chosen is None:
        chosen = rows[0][0]
    _child(chosen.id, permission)
    return chosen


def _select(student: Student) -> None:
    flask_session["active_student_id"] = student.id


def _scoped(endpoint: str, permission: str):
    child = _active_child(permission)
    if child is None:
        flash("No child is linked to your account yet.", "warning")
        return redirect(url_for("parent.children"))
    return redirect(url_for(endpoint, student_id=child.id))


# --------------------------------------------------------------------------
# Home & children
# --------------------------------------------------------------------------
@bp.get("/")
def home():
    session = current_session()
    rows = []
    for student, link in _children():
        data = None
        if session:
            try:
                data = child_overview(student, session.id)
            except Exception:  # a broken child record must not hide the others
                data = None
        rows.append({"student": student, "link": link, "data": data})

    announcements = (
        visible_announcements(current_user, session.id).limit(3).all() if session else []
    )
    return render_template(
        "parent/home.html", rows=rows, session=session, announcements=announcements
    )


@bp.get("/children")
def children():
    rows = _children()
    active_id = flask_session.get("active_student_id")
    return render_template("parent/children.html", rows=rows, active_id=active_id)


@bp.post("/children/<int:student_id>/select")
def select_child(student_id: int):
    student, _ = _child(student_id)
    _select(student)
    flash(f"Now viewing {student.full_name}.", "success")
    target = request.form.get("next") or url_for("parent.home")
    if not target.startswith("/parent/"):
        target = url_for("parent.home")
    return redirect(target)


# --------------------------------------------------------------------------
# Timetable
# --------------------------------------------------------------------------
@bp.get("/timetable")
def timetable():
    return _scoped("parent.child_timetable", "profile")


@bp.get("/children/<int:student_id>/timetable")
def child_timetable(student_id: int):
    student, _ = _child(student_id)
    _select(student)
    session = current_session()
    enrollment = student.enrollment_for(session.id) if session else None
    table = published_timetable(session.id) if session else None
    week = {}
    if table and enrollment:
        from ..services.timetable import section_week

        week = section_week(table, enrollment.section_id)
    return render_template(
        "parent/timetable.html",
        student=student,
        enrollment=enrollment,
        timetable=table,
        week=week,
        periods=table.periods if table else [],
        days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    )


# --------------------------------------------------------------------------
# Attendance
# --------------------------------------------------------------------------
@bp.get("/attendance")
def attendance():
    return _scoped("parent.child_attendance", "attendance")


@bp.get("/children/<int:student_id>/attendance")
def child_attendance(student_id: int):
    student, _ = _child(student_id, "attendance")
    _select(student)
    session = current_session()
    summary = attendance_service.student_summary(student.id, session.id if session else None)
    rows = summary["rows"][:60]
    return render_template(
        "parent/attendance.html", student=student, summary=summary, rows=rows
    )


# --------------------------------------------------------------------------
# Homework & materials
# --------------------------------------------------------------------------
@bp.get("/homework")
def homework():
    return _scoped("parent.child_homework", "homework")


@bp.get("/children/<int:student_id>/homework")
def child_homework(student_id: int):
    student, link = _child(student_id, "homework")
    _select(student)
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
    materials = (
        StudyMaterial.query.filter_by(
            session_id=session.id, school_class_id=enrollment.section.school_class_id
        ).all()
        if session and enrollment
        else []
    )
    return render_template(
        "parent/homework.html", student=student, rows=rows, materials=materials
    )


# --------------------------------------------------------------------------
# Examinations & results
# --------------------------------------------------------------------------
def _exams_for(student: Student) -> list[Examination]:
    session = current_session()
    enrollment = student.enrollment_for(session.id) if session else None
    if enrollment is None:
        return []
    class_id = enrollment.section.school_class_id
    return (
        Examination.query.join(
            ExaminationClass, ExaminationClass.examination_id == Examination.id
        )
        .filter(
            Examination.session_id == session.id,
            ExaminationClass.school_class_id == class_id,
        )
        .order_by(Examination.start_date.desc(), Examination.id.desc())
        .all()
    )


@bp.get("/exams")
def exams():
    return _scoped("parent.child_exams", "academics")


@bp.get("/children/<int:student_id>/exams")
def child_exams(student_id: int):
    student, _ = _child(student_id, "academics")
    _select(student)
    rows = _exams_for(student)
    return render_template("parent/exams.html", student=student, rows=rows)


@bp.get("/results")
def results():
    return _scoped("parent.child_results", "academics")


@bp.get("/children/<int:student_id>/results")
def child_results(student_id: int):
    student, _ = _child(student_id, "academics")
    _select(student)
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
            {
                "exam": exam,
                "summary": summary,
                "subjects": subject_breakdown(exam, student),
            }
        )
    return render_template("parent/results.html", student=student, rows=rows)


@bp.get("/report-cards")
def report_cards():
    return _scoped("parent.child_report_cards", "academics")


@bp.get("/children/<int:student_id>/report-cards")
def child_report_cards(student_id: int):
    student, _ = _child(student_id, "academics")
    _select(student)
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
    return render_template("parent/report_cards.html", student=student, cards=cards)


@bp.get("/report-cards/<int:card_id>.pdf")
def report_card_pdf(card_id: int):
    card = db.get_or_404(ReportCard, card_id)
    student, _ = _child(card.student_id, "academics")
    if card.status == ReportCardStatus.DRAFT:
        abort(404)
    return redirect(url_for("files.serve", file_uuid=card.pdf_file.uuid))


# --------------------------------------------------------------------------
# Fees
# --------------------------------------------------------------------------
@bp.get("/fees")
def fees():
    return _scoped("parent.child_fees", "fees")


@bp.get("/children/<int:student_id>/fees")
def child_fees(student_id: int):
    student, link = _child(student_id, "fees")
    _select(student)
    session = current_session()
    ledger = fee_service.student_ledger(student.id, session.id) if session else None
    payable = [row for row in ledger["rows"] if row.balance_paise > 0] if ledger else []
    return render_template(
        "parent/fees.html", student=student, ledger=ledger, payable=payable, link=link
    )


@bp.post("/children/<int:student_id>/fees/<int:fee_id>/pay")
def pay_fee(student_id: int, fee_id: int):
    student, _ = _child(student_id, "fees")
    fee = db.get_or_404(StudentFee, fee_id)
    if fee.student_id != student.id:
        abort(404)
    if fee.balance_paise <= 0:
        flash("That fee is already settled.", "info")
        return redirect(url_for("parent.child_fees", student_id=student.id))

    amount = fee.balance_paise
    raw = (request.form.get("amount") or "").strip()
    if raw:
        try:
            amount = to_paise(raw)
        except ValueError:
            flash("Enter a valid amount.", "error")
            return redirect(url_for("parent.child_fees", student_id=student.id))
    if amount <= 0 or amount > fee.balance_paise:
        flash("Enter an amount within the outstanding balance.", "error")
        return redirect(url_for("parent.child_fees", student_id=student.id))

    try:
        payment = fee_service.record_payment(
            student_fee=fee,
            amount_paise=amount,
            method="MOCK_ONLINE",
            actor_id=current_user.id,
            reference="Parent portal",
            notes="Online payment from the parent portal (mock gateway)",
        )
        flash(
            f"Payment recorded — receipt {payment.receipt_no}. "
            "The school office will confirm settlement.",
            "success",
        )
    except fee_service.FeeError as error:
        db.session.rollback()
        flash(str(error), "error")
    return redirect(url_for("parent.child_fees", student_id=student.id))


# --------------------------------------------------------------------------
# Announcements, leave, profile
# --------------------------------------------------------------------------
@bp.get("/announcements")
def announcements():
    session = current_session()
    rows = (
        visible_announcements(current_user, session.id).limit(50).all() if session else []
    )
    return render_template("parent/announcements.html", rows=rows)


@bp.route("/leave", methods=["GET", "POST"])
def leave():
    rows = _children()
    form = LeaveForm()
    form.student_id.choices = [
        (student.id, f"{student.full_name} · {student.admission_no}")
        for student, link in rows
        if link.can_apply_leave
    ]
    session = current_session()

    if form.validate_on_submit():
        student, _ = _child(form.student_id.data, "leave")
        if form.to_date.data < form.from_date.data:
            flash("The end date cannot be before the start date.", "error")
        else:
            application = LeaveApplication(
                school_id=current_user.school_id,
                session_id=session.id,
                scope=LeaveScope.STUDENT,
                student_id=student.id,
                applicant_user_id=current_user.id,
                from_date=form.from_date.data,
                to_date=form.to_date.data,
                leave_type=form.leave_type.data,
                reason=form.reason.data.strip(),
                status=LeaveStatus.PENDING,
            )
            if form.attachment.data and form.attachment.data.filename:
                try:
                    application.attachment_file_id = save_upload(
                        form.attachment.data, "leave", current_user.id
                    ).id
                except UploadError as error:
                    flash(str(error), "error")
                    return redirect(url_for("parent.leave"))
            db.session.add(application)
            db.session.commit()
            flash("Leave application submitted for review.", "success")
            return redirect(url_for("parent.leave"))

    applications = (
        LeaveApplication.query.filter_by(applicant_user_id=current_user.id)
        .order_by(LeaveApplication.created_at.desc())
        .all()
    )
    return render_template(
        "parent/leave.html", form=form, rows=applications, children=rows
    )


@bp.get("/profile")
def profile():
    return render_template("parent/profile.html", rows=_children())


@bp.post("/profile/notifications")
def notification_preference():
    guardian = current_user.guardian
    links = [link for link in guardian.links if link.status == LinkStatus.VERIFIED]
    wanted = not any(link.receive_notifications for link in links)
    for link in links:
        link.receive_notifications = wanted
    db.session.commit()
    flash(
        "Notifications will now be sent for your children."
        if wanted
        else "Notifications have been turned off.",
        "success",
    )
    return redirect(url_for("parent.profile"))
