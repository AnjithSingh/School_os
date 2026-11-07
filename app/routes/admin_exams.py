"""Examination management, marks approval, results and report cards."""
from __future__ import annotations

from collections import Counter, defaultdict

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..forms.exams import ExamForm, ExamSubjectForm, RemarkForm
from ..models import (
    Enrollment,
    ExamRemark,
    ExamType,
    Examination,
    ExaminationClass,
    ExaminationSubject,
    GradeScale,
    MarksEntrySheet,
    ResultSummary,
    Section,
    Student,
    Subject,
)
from ..models.base import utcnow
from ..models.enums import EnrollmentStatus, ExamStatus, ReportCardStatus, SheetStatus
from ..security.guards import permission_required
from ..services import academics
from ..services.exams import (
    MarksError,
    approve_sheet,
    compute_results,
    ensure_sheets,
    generate_report_card,
    latest_report_card,
    pending_sheets,
    publish,
    reopen_sheet,
    sheet_rows,
    subject_breakdown,
)
from ..services.audit import record
from ..services.settings import current_session

bp = Blueprint("admin_exams", __name__, url_prefix="/admin/exams")


@bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if current_user.scope.value != "STAFF":
        abort(403)


def _exam_or_404(exam_id: int) -> Examination:
    exam = db.session.get(Examination, exam_id)
    if exam is None:
        abort(404)
    return exam


@bp.route("/")
@permission_required("exams.manage")
def index():
    session = current_session()
    exams = (
        Examination.query.filter_by(session_id=session.id)
        .order_by(Examination.start_date.desc(), Examination.id.desc())
        .all()
        if session
        else []
    )
    form = ExamForm()
    form.exam_type_id.choices = [
        (t.id, t.name) for t in ExamType.query.order_by(ExamType.sequence).all()
    ]
    form.grading_scale_id.choices = [(0, "Default scale")] + [
        (s.id, s.name) for s in GradeScale.query.all()
    ]
    form.class_ids.choices = [(c.id, c.name) for c in academics.classes()]
    return render_template("admin/exams/index.html", exams=exams, form=form, session=session)


@bp.post("/new")
@permission_required("exams.manage")
def create():
    session = current_session()
    form = ExamForm()
    form.exam_type_id.choices = [(t.id, t.name) for t in ExamType.query.all()]
    form.grading_scale_id.choices = [(0, "Default")] + [(s.id, s.name) for s in GradeScale.query.all()]
    form.class_ids.choices = [(c.id, c.name) for c in academics.classes()]
    if not form.validate_on_submit():
        flash("Please check the examination details.", "error")
        return redirect(url_for("admin_exams.index"))

    if form.start_date.data and form.end_date.data and form.start_date.data > form.end_date.data:
        flash("The end date must be after the start date.", "error")
        return redirect(url_for("admin_exams.index"))

    exam = Examination(
        school_id=current_user.school_id,
        session_id=session.id,
        exam_type_id=form.exam_type_id.data,
        name=form.name.data.strip(),
        start_date=form.start_date.data,
        end_date=form.end_date.data,
        result_date=form.result_date.data,
        instructions=form.instructions.data,
        grading_scale_id=form.grading_scale_id.data or None,
        status=ExamStatus.DRAFT,
        created_by_id=current_user.id,
    )
    if exam.grading_scale_id is None:
        default_scale = GradeScale.query.filter_by(is_default=True).first()
        exam.grading_scale_id = default_scale.id if default_scale else None

    db.session.add(exam)
    db.session.flush()
    for class_id in form.class_ids.data:
        db.session.add(
            ExaminationClass(
                school_id=current_user.school_id,
                examination_id=exam.id,
                school_class_id=class_id,
            )
        )
    record("exam.created", "Examination", exam.id, summary=exam.name)
    db.session.commit()
    flash("Examination created. Add subjects to build the schedule.", "success")
    return redirect(url_for("admin_exams.detail", exam_id=exam.id))


@bp.route("/<int:exam_id>")
@permission_required("exams.manage")
def detail(exam_id: int):
    exam = _exam_or_404(exam_id)
    ensure_sheets(exam)
    form = ExamSubjectForm()
    form.school_class_id.choices = [
        (c.id, c.name) for c in academics.classes()
    ]
    form.subject_id.choices = [(s.id, s.name) for s in Subject.query.order_by(Subject.name)]
    sheets = (
        MarksEntrySheet.query.join(MarksEntrySheet.exam_subject)
        .filter(ExaminationSubject.examination_id == exam.id)
        .order_by(MarksEntrySheet.section_id)
        .all()
    )
    return render_template(
        "admin/exams/detail.html", exam=exam, form=form, sheets=sheets,
        classes=academics.classes(), subjects=Subject.query.order_by(Subject.name).all(),
    )


@bp.post("/<int:exam_id>/subjects")
@permission_required("exams.manage")
def add_subject(exam_id: int):
    exam = _exam_or_404(exam_id)
    form = ExamSubjectForm()
    form.school_class_id.choices = [(c.id, c.name) for c in academics.classes()]
    form.subject_id.choices = [(s.id, s.name) for s in Subject.query.all()]
    if not form.validate_on_submit():
        flash("Please check the subject details.", "error")
        return redirect(url_for("admin_exams.detail", exam_id=exam.id))

    existing = ExaminationSubject.query.filter_by(
        examination_id=exam.id,
        school_class_id=form.school_class_id.data,
        subject_id=form.subject_id.data,
    ).first()
    if existing:
        flash("That subject is already part of this examination.", "error")
        return redirect(url_for("admin_exams.detail", exam_id=exam.id))

    if form.pass_marks.data > form.max_marks.data:
        flash("Passing marks cannot exceed maximum marks.", "error")
        return redirect(url_for("admin_exams.detail", exam_id=exam.id))

    db.session.add(
        ExaminationSubject(
            school_id=exam.school_id,
            examination_id=exam.id,
            school_class_id=form.school_class_id.data,
            subject_id=form.subject_id.data,
            exam_date=form.exam_date.data,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            room=form.room.data,
            max_marks=form.max_marks.data,
            pass_marks=form.pass_marks.data,
        )
    )
    db.session.commit()
    ensure_sheets(exam)
    flash("Subject added and marks sheets prepared.", "success")
    return redirect(url_for("admin_exams.detail", exam_id=exam.id))


@bp.post("/<int:exam_id>/status")
@permission_required("exams.manage")
def change_status(exam_id: int):
    exam = _exam_or_404(exam_id)
    target = request.form.get("status")
    allowed = {
        "SCHEDULED": ExamStatus.SCHEDULED,
        "MARKS_ENTRY": ExamStatus.MARKS_ENTRY,
        "APPROVED": ExamStatus.APPROVED,
        "ARCHIVED": ExamStatus.ARCHIVED,
    }
    if target not in allowed:
        flash("Unknown examination state.", "error")
        return redirect(url_for("admin_exams.detail", exam_id=exam.id))

    if target == "MARKS_ENTRY" and not exam.subjects:
        flash("Add at least one subject before opening marks entry.", "error")
        return redirect(url_for("admin_exams.detail", exam_id=exam.id))

    exam.status = allowed[target]
    record("exam.status", "Examination", exam.id, summary=target)
    db.session.commit()
    flash(f"Examination moved to {exam.status.value.replace('_', ' ').title()}.", "success")
    return redirect(url_for("admin_exams.detail", exam_id=exam.id))


@bp.route("/<int:exam_id>/sheets/<int:sheet_id>")
@permission_required("exams.manage")
def sheet(exam_id: int, sheet_id: int):
    exam = _exam_or_404(exam_id)
    sheet = db.get_or_404(MarksEntrySheet, sheet_id)
    if sheet.exam_subject.examination_id != exam.id:
        abort(404)
    return render_template(
        "admin/exams/sheet.html", exam=exam, sheet=sheet, rows=sheet_rows(sheet)
    )


@bp.post("/<int:exam_id>/sheets/<int:sheet_id>/approve")
@permission_required("marks.approve")
def approve(exam_id: int, sheet_id: int):
    sheet = db.get_or_404(MarksEntrySheet, sheet_id)
    try:
        approve_sheet(sheet, current_user.id)
        flash("Marks sheet approved.", "success")
    except MarksError as error:
        flash(str(error), "error")
    return redirect(url_for("admin_exams.sheet", exam_id=exam_id, sheet_id=sheet_id))


@bp.post("/<int:exam_id>/sheets/<int:sheet_id>/reopen")
@permission_required("marks.approve")
def reopen(exam_id: int, sheet_id: int):
    sheet = db.get_or_404(MarksEntrySheet, sheet_id)
    reason = request.form.get("reason", "").strip()
    if not reason:
        flash("A reason is required to reopen a marks sheet.", "error")
    else:
        reopen_sheet(sheet, current_user.id, reason)
        flash("Sheet reopened for correction.", "success")
    return redirect(url_for("admin_exams.sheet", exam_id=exam_id, sheet_id=sheet_id))


@bp.route("/progress")
@permission_required("exams.manage")
def progress():
    session = current_session()
    query = (
        MarksEntrySheet.query.join(MarksEntrySheet.exam_subject)
        .join(ExaminationSubject.examination)
        .filter(Examination.session_id == session.id)
        if session
        else MarksEntrySheet.query.filter(db.false())
    )
    status = request.args.get("status", "")
    if status:
        query = query.filter(MarksEntrySheet.status == SheetStatus(status))
    sheets = query.order_by(MarksEntrySheet.status, MarksEntrySheet.id).all()
    return render_template(
        "admin/exams/progress.html", sheets=sheets, status=status, statuses=SheetStatus
    )


@bp.post("/<int:exam_id>/compute")
@permission_required("exams.manage")
def compute(exam_id: int):
    exam = _exam_or_404(exam_id)
    stats = compute_results(exam, current_user.id)
    exam.status = ExamStatus.APPROVED
    db.session.commit()
    message = f"{stats['computed']} results computed."
    if stats["incomplete_sheets"]:
        message += f" {stats['incomplete_sheets']} sheets were not approved."
    flash(message, "success" if not stats["incomplete_sheets"] else "warning")
    return redirect(url_for("admin_exams.results", exam_id=exam.id))


@bp.route("/<int:exam_id>/results")
@permission_required("exams.manage")
def results(exam_id: int):
    exam = _exam_or_404(exam_id)
    rows = (
        ResultSummary.query.filter_by(examination_id=exam.id)
        .join(ResultSummary.student)
        .order_by(Student.first_name)
        .all()
    )
    remarks = {
        r.student_id: r
        for r in ExamRemark.query.filter_by(examination_id=exam.id).all()
    }
    return render_template(
        "admin/exams/results.html", exam=exam, rows=rows, remarks=remarks, RemarkForm=RemarkForm
    )


@bp.post("/<int:exam_id>/publish")
@permission_required("results.publish")
def publish_results(exam_id: int):
    exam = _exam_or_404(exam_id)
    if not exam.results.count():
        flash("Compute results before publishing.", "error")
        return redirect(url_for("admin_exams.results", exam_id=exam.id))
    publish(exam, current_user.id)
    flash("Results published. Families have been notified.", "success")
    return redirect(url_for("admin_exams.results", exam_id=exam.id))


@bp.route("/<int:exam_id>/remarks/<int:student_id>", methods=["POST"])
@permission_required("results.publish")
def save_remark(exam_id: int, student_id: int):
    exam = _exam_or_404(exam_id)
    remark = ExamRemark.query.filter_by(
        examination_id=exam.id, student_id=student_id
    ).first()
    if remark is None:
        remark = ExamRemark(
            school_id=exam.school_id, examination_id=exam.id, student_id=student_id
        )
        db.session.add(remark)
    remark.teacher_remark = request.form.get("teacher_remark", "").strip() or None
    remark.principal_remark = request.form.get("principal_remark", "").strip() or None
    remark.written_by_id = current_user.id
    db.session.commit()
    flash("Remarks saved.", "success")
    return redirect(url_for("admin_exams.results", exam_id=exam.id))


@bp.route("/<int:exam_id>/report-cards", methods=["GET", "POST"])
@permission_required("results.publish")
def report_cards(exam_id: int):
    exam = _exam_or_404(exam_id)
    if request.method == "POST":
        rows = ResultSummary.query.filter_by(examination_id=exam.id).all()
        generated = 0
        for row in rows:
            try:
                generate_report_card(exam, row.student, current_user.id)
                generated += 1
            except MarksError:
                continue
        flash(f"{generated} report cards generated.", "success")
        return redirect(url_for("admin_exams.report_cards", exam_id=exam.id))

    rows = ResultSummary.query.filter_by(examination_id=exam.id).all()
    cards = {}
    for row in rows:
        cards[row.student_id] = latest_report_card(exam.id, row.student_id)
    return render_template(
        "admin/exams/report_cards.html", exam=exam, rows=rows, cards=cards
    )


@bp.route("/<int:exam_id>/analytics")
@permission_required("analytics.view")
def analytics(exam_id: int):
    exam = _exam_or_404(exam_id)
    results = ResultSummary.query.filter_by(examination_id=exam.id).all()
    percentages = [r.percentage for r in results]
    pass_count = sum(1 for r in results if r.result_status.value == "PASS")
    grade_counts = Counter(r.grade or "—" for r in results)

    by_class: dict[str, list[float]] = defaultdict(list)
    for result in results:
        section = result.section
        label = section.label if section else "—"
        by_class[label].append(result.percentage)

    subject_rows = []
    for exam_subject in exam.subjects:
        sheets = MarksEntrySheet.query.filter_by(examination_subject_id=exam_subject.id).all()
        records = [rec for sheet in sheets for rec in sheet.records if rec.marks_obtained is not None]
        if not records:
            continue
        average = sum(r.marks_obtained for r in records) / len(records)
        subject_rows.append(
            {
                "subject": exam_subject.subject.name,
                "class": exam_subject.school_class.name,
                "max": exam_subject.max_marks,
                "average": round(average, 1),
                "percentage": round(average / exam_subject.max_marks * 100, 1),
                "count": len(records),
                "highest": max(r.marks_obtained for r in records),
                "lowest": min(r.marks_obtained for r in records),
            }
        )

    weak = [r for r in results if r.subjects_failed >= 2]
    summary = {
        "count": len(results),
        "average": round(sum(percentages) / len(percentages), 2) if percentages else 0,
        "highest": round(max(percentages), 2) if percentages else 0,
        "lowest": round(min(percentages), 2) if percentages else 0,
        "pass_rate": round(pass_count / len(results) * 100, 1) if results else 0,
        "pass_count": pass_count,
    }
    return render_template(
        "admin/exams/analytics.html",
        exam=exam,
        summary=summary,
        grade_counts=grade_counts,
        by_class={k: round(sum(v) / len(v), 2) for k, v in by_class.items()},
        subject_rows=subject_rows,
        weak=weak,
    )
