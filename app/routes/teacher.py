"""Teacher workspace.

Every view is scoped to the signed-in teacher's own sections. Section ids are
re-derived from allocations on each request so a URL can never widen access.
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
    url_for,
)
from flask_login import current_user

from ..extensions import db
from ..forms.comms import AnnouncementForm, LeaveForm
from ..forms.operations import HomeworkForm, HomeworkReviewForm, StudyMaterialForm
from ..models import (
    Announcement,
    Homework,
    HomeworkSubmission,
    LeaveApplication,
    MarksEntrySheet,
    SchoolClass,
    Section,
    Student,
    StudyMaterial,
    Subject,
    SubjectAllocation,
)
from ..models.base import utcnow
from ..models.enums import (
    AnnouncementScope,
    AnnouncementStatus,
    EnrollmentStatus,
    LeaveScope,
    LeaveStatus,
    SheetStatus,
    SubmissionStatus,
)
from ..security.guards import roles_required
from ..security.scoping import current_staff, teacher_section_ids
from ..services import academics
from ..services import attendance as attendance_service
from ..services.audit import record
from ..services.communication import visible_announcements
from ..services.dashboard import teacher_overview
from ..services.exams import MarksError, save_marks, sheet_rows
from ..services.settings import current_session
from ..services.timetable import day_entries, published_timetable, teacher_week
from ..utils.uploads import UploadError, save_upload

bp = Blueprint("teacher", __name__, url_prefix="/teacher")

MINIMAL_STAFF_ROLES = ("TEACHER",)


@bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if current_user.role.value != "TEACHER":
        abort(403)
    if current_staff() is None:
        abort(403)


def _staff():
    staff = current_staff()
    if staff is None:
        abort(403)
    return staff


def _my_sections() -> list[Section]:
    ids = teacher_section_ids()
    if not ids:
        return []
    return (
        Section.query.filter(Section.id.in_(ids))
        .order_by(Section.school_class_id, Section.name)
        .all()
    )


def _own_section(section_id: int) -> Section:
    section = db.session.get(Section, section_id)
    if section is None or section.id not in teacher_section_ids():
        abort(404)
    return section


@bp.route("/")
def dashboard():
    staff = _staff()
    return render_template("teacher/dashboard.html", **teacher_overview(staff))


@bp.route("/timetable")
def timetable():
    staff = _staff()
    session = current_session()
    if session is None:
        flash("No academic year is active yet.", "error")
        return render_template("teacher/timetable.html", timetable=None, week={}, periods=[])

    table = published_timetable(session.id)
    if table is None:
        return render_template("teacher/timetable.html", timetable=None, week={}, periods=[])

    week = teacher_week(table, staff.id)
    return render_template(
        "teacher/timetable.html",
        timetable=table,
        week=week,
        periods=table.periods,
        days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    )


@bp.route("/classes")
def classes():
    staff = _staff()
    session = current_session()
    sections = _my_sections()
    allocations = (
        SubjectAllocation.query.filter_by(teacher_id=staff.id).all() if session else []
    )
    by_section: dict[int, list] = {}
    for row in allocations:
        by_section.setdefault(row.section_id, []).append(row)

    roster = []
    for section in sections:
        count = section.enrollments.filter_by(status=EnrollmentStatus.ACTIVE).count()
        roster.append(
            {
                "section": section,
                "subjects": by_section.get(section.id, []),
                "count": count,
                "is_class_teacher": section.class_teacher_id == staff.id,
            }
        )
    return render_template("teacher/classes.html", roster=roster)


@bp.route("/classes/<int:section_id>")
def class_detail(section_id: int):
    section = _own_section(section_id)
    session = current_session()
    enrollments = attendance_service.enrolled_students(section.id)
    subjects = [
        row
        for row in SubjectAllocation.query.filter_by(
            section_id=section.id, teacher_id=_staff().id
        ).all()
    ]
    return render_template(
        "teacher/class_detail.html",
        section=section,
        enrollments=enrollments,
        subjects=subjects,
        session=session,
    )


# --------------------------------------------------------------------------
# Attendance
# --------------------------------------------------------------------------
@bp.route("/attendance")
def attendance():
    sections = _my_sections()
    if not sections:
        return render_template(
            "teacher/attendance.html",
            sections=[],
            section=None,
            rows=[],
            records={},
            on_date=date.today(),
            holiday=False,
            statuses=list(attendance_service.AttendanceStatus),
        )

    section_id = request.args.get("section_id", type=int)
    section = (
        db.session.get(Section, section_id) if section_id else sections[0]
    )
    if section is None or section.id not in {s.id for s in sections}:
        abort(404)

    raw_date = request.args.get("date")
    try:
        on_date = date.fromisoformat(raw_date) if raw_date else date.today()
    except ValueError:
        on_date = date.today()

    session = current_session()
    records = attendance_service.existing_records(section.id, on_date)
    rows = attendance_service.enrolled_students(section.id)
    return render_template(
        "teacher/attendance.html",
        sections=sections,
        section=section,
        rows=rows,
        records=records,
        on_date=on_date,
        holiday=attendance_service.is_holiday(session.id, on_date) if session else False,
        statuses=list(attendance_service.AttendanceStatus),
    )


@bp.post("/attendance")
def save_attendance():
    sections = {s.id for s in _my_sections()}
    try:
        section_id = int(request.form.get("section_id", "0"))
    except ValueError:
        abort(400)
    if section_id not in sections:
        abort(404)
    section = db.session.get(Section, section_id)
    raw_date = request.form.get("date")
    try:
        on_date = date.fromisoformat(raw_date) if raw_date else date.today()
    except ValueError:
        on_date = date.today()

    entries: dict[int, str] = {}
    remarks: dict[int, str] = {}
    for key, value in request.form.items():
        if key.startswith("status_"):
            try:
                entries[int(key.split("_", 1)[1])] = value
            except ValueError:
                continue
        elif key.startswith("remarks_"):
            try:
                remarks[int(key.split("_", 1)[1])] = value
            except ValueError:
                continue

    try:
        result = attendance_service.save_section_attendance(
            section=section,
            on_date=on_date,
            entries=entries,
            remarks=remarks,
            actor_id=current_user.id,
            is_admin=False,
        )
        flash(
            f"Attendance saved — {result['created']} new, {result['updated']} updated.",
            "success",
        )
    except attendance_service.AttendanceError as error:
        db.session.rollback()
        flash(str(error), "error")

    return redirect(
        url_for("teacher.attendance", section_id=section.id, date=on_date.isoformat())
    )


# --------------------------------------------------------------------------
# Homework
# --------------------------------------------------------------------------
@bp.route("/homework")
def homework():
    staff = _staff()
    session = current_session()
    if session is None:
        return render_template("teacher/homework.html", rows=[], sections=[], subjects=[])

    rows = (
        Homework.query.filter_by(teacher_id=staff.id, session_id=session.id)
        .order_by(Homework.assigned_on.desc(), Homework.id.desc())
        .all()
    )
    form = HomeworkForm()
    sections = _my_sections()
    form.section_id.choices = [(s.id, s.label) for s in sections]
    subject_ids = {
        row.subject_id
        for row in SubjectAllocation.query.filter_by(teacher_id=staff.id).all()
    }
    form.subject_id.choices = [
        (s.id, s.name) for s in Subject.query.filter(Subject.id.in_(subject_ids)).all()
    ]
    form.assigned_on.data = date.today()

    return render_template(
        "teacher/homework.html", rows=rows, form=form, sections=sections
    )


@bp.post("/homework")
def create_homework():
    staff = _staff()
    session = current_session()
    sections = {s.id for s in _my_sections()}
    form = HomeworkForm()
    form.section_id.choices = [(sid, str(sid)) for sid in sections]
    form.subject_id.choices = [
        (row.subject_id, str(row.subject_id))
        for row in SubjectAllocation.query.filter_by(teacher_id=staff.id).all()
    ]
    if session is None or not form.validate_on_submit():
        flash("Please check the homework details.", "error")
        return redirect(url_for("teacher.homework"))

    if form.section_id.data not in sections:
        abort(404)

    attachment_id = None
    if form.attachment.data and form.attachment.data.filename:
        try:
            attachment_id = save_upload(form.attachment.data, "homework", current_user.id).id
        except UploadError as error:
            flash(str(error), "error")
            return redirect(url_for("teacher.homework"))

    item = Homework(
        school_id=current_user.school_id,
        session_id=session.id,
        section_id=form.section_id.data,
        subject_id=form.subject_id.data,
        teacher_id=staff.id,
        title=form.title.data.strip(),
        description=(form.description.data or "").strip() or None,
        assigned_on=form.assigned_on.data or date.today(),
        due_at=form.due_at.data,
        max_marks=form.max_marks.data,
        attachment_file_id=attachment_id,
        status="PUBLISHED",
    )
    db.session.add(item)
    record("homework.published", "Homework", None, summary=item.title, actor_id=current_user.id)
    db.session.commit()
    flash("Homework published to the class.", "success")
    return redirect(url_for("teacher.homework_detail", homework_id=item.id))


@bp.route("/homework/<int:homework_id>")
def homework_detail(homework_id: int):
    staff = _staff()
    item = db.get_or_404(Homework, homework_id)
    if item.teacher_id != staff.id:
        abort(404)
    submissions = {s.student_id: s for s in item.submissions}
    enrollments = attendance_service.enrolled_students(item.section_id)
    return render_template(
        "teacher/homework_detail.html",
        homework=item,
        submissions=submissions,
        enrollments=enrollments,
    )


@bp.post("/homework/<int:homework_id>/submissions/<int:student_id>")
def review_submission(homework_id: int, student_id: int):
    staff = _staff()
    item = db.get_or_404(Homework, homework_id)
    if item.teacher_id != staff.id:
        abort(404)
    submission = HomeworkSubmission.query.filter_by(
        homework_id=item.id, student_id=student_id
    ).first()
    if submission is None:
        submission = HomeworkSubmission(
            school_id=item.school_id, homework_id=item.id, student_id=student_id
        )
        db.session.add(submission)
    form = HomeworkReviewForm()
    if form.validate_on_submit():
        submission.remarks = form.remarks.data
        submission.marks = form.marks.data
        submission.status = SubmissionStatus.REVIEWED
        submission.reviewed_by_id = current_user.id
        submission.reviewed_at = utcnow()
        submission.submitted_at = submission.submitted_at or utcnow()
        db.session.commit()
        flash("Submission reviewed.", "success")
    return redirect(url_for("teacher.homework_detail", homework_id=item.id))


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------
@bp.route("/materials", methods=["GET", "POST"])
def materials():
    staff = _staff()
    session = current_session()
    form = StudyMaterialForm()
    classes = SchoolClass.query.order_by(SchoolClass.display_order).all()
    form.school_class_id.choices = [(c.id, c.name) for c in classes]
    form.section_id.choices = [(0, "All sections")] + [
        (s.id, s.label) for s in _my_sections()
    ]
    subject_ids = {
        row.subject_id
        for row in SubjectAllocation.query.filter_by(teacher_id=staff.id).all()
    }
    form.subject_id.choices = [
        (s.id, s.name) for s in Subject.query.filter(Subject.id.in_(subject_ids)).all()
    ] or [(s.id, s.name) for s in Subject.query.order_by(Subject.name).all()]

    if form.validate_on_submit():
        file_id = None
        if form.file.data and form.file.data.filename:
            try:
                file_id = save_upload(form.file.data, "materials", current_user.id).id
            except UploadError as error:
                flash(str(error), "error")
                return redirect(url_for("teacher.materials"))
        material = StudyMaterial(
            school_id=current_user.school_id,
            session_id=session.id if session else None,
            school_class_id=form.school_class_id.data,
            section_id=form.section_id.data or None,
            subject_id=form.subject_id.data,
            title=form.title.data.strip(),
            description=(form.description.data or "").strip() or None,
            file_id=file_id,
            uploaded_by_id=current_user.id,
            is_published=True,
        )
        db.session.add(material)
        db.session.commit()
        flash("Study material published.", "success")
        return redirect(url_for("teacher.materials"))

    section_ids = {s.id for s in _my_sections()}
    query = StudyMaterial.query.filter_by(session_id=session.id) if session else StudyMaterial.query.filter(db.false())
    rows = query.all()
    visible = [
        row
        for row in rows
        if row.uploaded_by_id == current_user.id
        or (row.section_id is None and row.school_class_id in {s.school_class_id for s in _my_sections()})
        or row.section_id in section_ids
    ]
    visible.sort(key=lambda r: r.created_at, reverse=True)
    return render_template("teacher/materials.html", form=form, rows=visible)


# --------------------------------------------------------------------------
# Marks
# --------------------------------------------------------------------------
@bp.route("/marks")
def marks():
    staff = _staff()
    sheets = (
        MarksEntrySheet.query.filter_by(teacher_id=staff.id)
        .order_by(MarksEntrySheet.id.desc())
        .all()
    )
    return render_template("teacher/marks.html", sheets=sheets, statuses=SheetStatus)


@bp.route("/marks/<int:sheet_id>", methods=["GET", "POST"])
def marks_sheet(sheet_id: int):
    staff = _staff()
    sheet = db.get_or_404(MarksEntrySheet, sheet_id)
    if sheet.teacher_id != staff.id:
        abort(404)

    if request.method == "POST":
        entries: dict[int, dict] = {}
        for key, value in request.form.items():
            if not key.startswith("marks_"):
                continue
            try:
                student_id = int(key.split("_", 1)[1])
            except ValueError:
                continue
            entries[student_id] = {
                "marks": value,
                "status": request.form.get(f"status_{student_id}", "PRESENT"),
                "remarks": request.form.get(f"remarks_{student_id}", ""),
            }
        submit = request.form.get("action") == "submit"
        try:
            save_marks(sheet, entries, current_user.id, submit=submit,
                       reason=request.form.get("reason"))
            flash("Marks submitted for approval." if submit else "Draft saved.", "success")
            return redirect(url_for("teacher.marks"))
        except (MarksError, ValueError) as error:
            db.session.rollback()
            flash(str(error), "error")

    return render_template(
        "teacher/marks_sheet.html", sheet=sheet, rows=sheet_rows(sheet)
    )


# --------------------------------------------------------------------------
# Announcements, leave, profile
# --------------------------------------------------------------------------
@bp.get("/announcements")
def announcements():
    session = current_session()
    rows = (
        visible_announcements(current_user, session.id).limit(50).all() if session else []
    )
    return render_template("teacher/announcements.html", rows=rows)


@bp.route("/leave", methods=["GET", "POST"])
def leave():
    staff = _staff()
    session = current_session()
    form = LeaveForm()
    form.student_id.choices = [(0, "Not applicable")]

    if form.validate_on_submit():
        application = LeaveApplication(
            school_id=current_user.school_id,
            session_id=session.id,
            scope=LeaveScope.STAFF,
            staff_id=staff.id,
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
                return redirect(url_for("teacher.leave"))
        db.session.add(application)
        db.session.commit()
        flash("Leave application submitted.", "success")
        return redirect(url_for("teacher.leave"))

    rows = (
        LeaveApplication.query.filter_by(staff_id=staff.id)
        .order_by(LeaveApplication.created_at.desc())
        .all()
    )
    return render_template("teacher/leave.html", form=form, rows=rows)


@bp.get("/profile")
def profile():
    staff = _staff()
    session = current_session()
    allocations = (
        SubjectAllocation.query.filter_by(teacher_id=staff.id).all() if session else []
    )
    classes_led = Section.query.filter_by(class_teacher_id=staff.id).all()
    return render_template(
        "teacher/profile.html",
        staff=staff,
        allocations=allocations,
        classes_led=classes_led,
    )
