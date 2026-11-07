"""Student management."""
from __future__ import annotations

import csv
import io
from datetime import date

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user

from ..extensions import db
from ..forms.people import GuardianForm, PromotionForm, StudentForm
from ..models import (
    AcademicSession,
    Enrollment,
    Guardian,
    GuardianStudentLink,
    SchoolClass,
    Section,
    Student,
    StudentDocument,
)
from ..models.enums import EnrollmentStatus, Gender, StudentStatus
from ..security.guards import permission_required
from ..services import students as student_service
from ..services.audit import record
from ..services.settings import current_session
from ..utils.uploads import UploadError, save_upload
from ..utils.pagination import paginate

bp = Blueprint("admin_students", __name__, url_prefix="/admin/students")


@bp.before_request
def _guard():
    from flask import abort as _abort

    from flask_login import current_user as _user

    if not _user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if _user.scope.value != "STAFF":
        _abort(403)


def _form_choices(form: StudentForm, session):
    classes = SchoolClass.query.order_by(SchoolClass.display_order).all()
    sections = (
        Section.query.filter_by(session_id=session.id, is_active=True)
        .order_by(Section.school_class_id, Section.name)
        .all()
        if session
        else []
    )
    form.class_id.choices = [(c.id, c.name) for c in classes]
    form.section_id.choices = [(s.id, s.label) for s in sections]


@bp.route("/")
@permission_required("students.view")
def index():
    session = current_session()
    q = request.args.get("q", "").strip()
    class_id = request.args.get("class_id", type=int)
    section_id = request.args.get("section_id", type=int)
    status = request.args.get("status", "")

    query = student_service.list_students(
        q=q,
        session_id=session.id if session else None,
        class_id=class_id,
        section_id=section_id,
        status=StudentStatus(status) if status else None,
    )
    page = paginate(query, per_page=20)
    classes = SchoolClass.query.order_by(SchoolClass.display_order).all()
    sections = (
        Section.query.filter_by(session_id=session.id, is_active=True).all() if session else []
    )
    return render_template(
        "admin/students/index.html",
        page=page,
        classes=classes,
        sections=sections,
        q=q,
        class_id=class_id,
        section_id=section_id,
        status=status,
        statuses=StudentStatus,
    )


@bp.route("/new", methods=["GET", "POST"])
@permission_required("students.manage")
def create():
    session = current_session()
    if session is None:
        flash("Create an academic year before admitting students.", "error")
        return redirect(url_for("admin.settings"))

    form = StudentForm()
    _form_choices(form, session)
    if request.method == "GET":
        form.admission_date.data = date.today()
        form.admission_no.data = student_service.next_admission_no(current_user.school_id)
        first = SchoolClass.query.order_by(SchoolClass.display_order).first()
        if first:
            form.class_id.data = first.id

    if form.validate_on_submit():
        section = db.session.get(Section, form.section_id.data)
        if section is None or section.session_id != session.id:
            abort(404)
        photo_id = None
        if form.photo.data and form.photo.data.filename:
            try:
                photo_id = save_upload(form.photo.data, "students", current_user.id).id
            except UploadError as error:
                flash(str(error), "error")
                return render_template("admin/students/form.html", form=form, student=None)

        if Student.query.filter_by(admission_no=form.admission_no.data.strip()).first():
            form.admission_no.errors.append("That admission number is already in use.")
        else:
            student = student_service.create_student(
                school_id=current_user.school_id,
                session=session,
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                section=section,
                dob=form.dob.data,
                gender=Gender(form.gender.data) if form.gender.data else None,
                admission_no=form.admission_no.data,
                admission_date=form.admission_date.data,
                roll_no=form.roll_no.data,
                photo_file_id=photo_id,
                address=form.address.data,
                city=form.city.data,
                state=form.state.data,
                pincode=form.pincode.data,
                phone=form.phone.data,
                email=form.email.data,
                emergency_name=form.emergency_name.data,
                emergency_phone=form.emergency_phone.data,
                category=form.category.data,
                previous_school=form.previous_school.data,
                previous_class=form.previous_class.data,
                notes=form.notes.data,
                actor_id=current_user.id,
            )
            db.session.commit()
            flash(f"{student.full_name} admitted successfully.", "success")
            return redirect(url_for("admin_students.profile", student_id=student.id))

    return render_template("admin/students/form.html", form=form, student=None)


@bp.route("/<int:student_id>")
@permission_required("students.view")
def profile(student_id: int):
    from ..services import attendance as attendance_service
    from ..services import fees as fee_service
    from ..services.exams import subject_breakdown

    student = db.get_or_404(Student, student_id)
    session = current_session()
    enrollment = student.enrollment_for(session.id) if session else None
    attendance = attendance_service.student_summary(student.id, session.id if session else None)
    ledger = fee_service.student_ledger(student.id, session.id) if session else None
    links = student_service.guardians_of(student)

    results = []
    if session:
        from ..models import Examination, ResultSummary

        rows = (
            ResultSummary.query.filter_by(student_id=student.id)
            .join(ResultSummary.examination)
            .filter(Examination.session_id == session.id)
            .order_by(Examination.start_date.desc())
            .all()
        )
        results = rows

    return render_template(
        "admin/students/profile.html",
        student=student,
        session=session,
        enrollment=enrollment,
        attendance=attendance,
        ledger=ledger,
        links=links,
        results=results,
        enrollment_history=student.enrollments,
    )


@bp.route("/<int:student_id>/edit", methods=["GET", "POST"])
@permission_required("students.manage")
def edit(student_id: int):
    student = db.get_or_404(Student, student_id)
    session = current_session()
    enrollment = student.enrollment_for(session.id) if session else None
    form = StudentForm(obj=student)
    _form_choices(form, session)
    if request.method == "GET" and enrollment:
        form.class_id.data = enrollment.section.school_class_id
        form.section_id.data = enrollment.section_id
        form.roll_no.data = enrollment.roll_no

    if form.validate_on_submit():
        section = db.session.get(Section, form.section_id.data)
        if section is None or section.session_id != session.id:
            abort(404)
        student_service.update_student(
            student,
            {
                "first_name": form.first_name.data.strip(),
                "last_name": form.last_name.data.strip(),
                "dob": form.dob.data,
                "gender": Gender(form.gender.data) if form.gender.data else None,
                "address": form.address.data,
                "city": form.city.data,
                "state": form.state.data,
                "pincode": form.pincode.data,
                "phone": form.phone.data,
                "email": form.email.data,
                "emergency_name": form.emergency_name.data,
                "emergency_phone": form.emergency_phone.data,
                "category": form.category.data,
                "blood_group": form.blood_group.data,
            },
        )
        student.admission_no = form.admission_no.data.strip() or student.admission_no
        if enrollment:
            enrollment.section_id = section.id
            enrollment.roll_no = form.roll_no.data
        if form.photo.data and form.photo.data.filename:
            try:
                student.photo_file_id = save_upload(
                    form.photo.data, "students", current_user.id
                ).id
            except UploadError as error:
                flash(str(error), "error")
        record("student.updated", "Student", student.id, summary=student.full_name)
        db.session.commit()
        flash("Student record updated.", "success")
        return redirect(url_for("admin_students.profile", student_id=student.id))
    return render_template("admin/students/form.html", form=form, student=student)


@bp.route("/<int:student_id>/guardians", methods=["POST"])
@permission_required("parents.manage")
def add_guardian(student_id: int):
    student = db.get_or_404(Student, student_id)
    form = GuardianForm()
    if form.validate_on_submit():
        if form.username.data and not form.password.data:
            flash("Set a temporary password when creating a portal login.", "error")
            return redirect(url_for("admin_students.profile", student_id=student.id))
        guardian = student_service.create_guardian(
            school_id=student.school_id,
            full_name=form.full_name.data,
            relationship=form.relationship.data,
            student=student,
            phone=form.phone.data,
            email=form.email.data,
            occupation=form.occupation.data,
            address=form.address.data,
            username=form.username.data,
            password=form.password.data,
            actor_id=current_user.id,
            verify=True,
            permissions={
                "academics": form.can_view_academics.data,
                "attendance": form.can_view_attendance.data,
                "fees": form.can_pay_fees.data,
                "homework": form.can_view_homework.data,
                "leave": form.can_apply_leave.data,
                "notifications": form.receive_notifications.data,
            },
        )
        db.session.commit()
        flash(f"{guardian.full_name} linked to {student.full_name}.", "success")
    else:
        flash("Please check the guardian details.", "error")
    return redirect(url_for("admin_students.profile", student_id=student.id))


@bp.route("/<int:student_id>/transfer", methods=["POST"])
@permission_required("students.manage")
def transfer(student_id: int):
    student = db.get_or_404(Student, student_id)
    reason = request.form.get("reason", "").strip() or "Transfer requested by family"
    student_service.transfer_student(student, reason, current_user.id)
    flash(f"{student.full_name} marked as transferred.", "success")
    return redirect(url_for("admin_students.profile", student_id=student.id))


@bp.route("/promote", methods=["GET", "POST"])
@permission_required("students.manage")
def promote():
    sessions = AcademicSession.query.order_by(AcademicSession.start_date.desc()).all()
    if len(sessions) < 2:
        flash("Create the next academic year before promoting students.", "error")
        return redirect(url_for("admin.settings"))

    form = PromotionForm()
    form.from_session_id.choices = [(s.id, s.name) for s in sessions]
    form.to_session_id.choices = [(s.id, s.name) for s in sessions]

    preview = None
    if request.method == "POST":
        if not form.from_session_id.data or not form.to_session_id.data:
            flash("Select both academic years.", "error")
        elif form.from_session_id.data == form.to_session_id.data:
            flash("Choose two different academic years.", "error")
        else:
            source = db.session.get(AcademicSession, form.from_session_id.data)
            target = db.session.get(AcademicSession, form.to_session_id.data)
            if form.confirm.data:
                counts = student_service.promote_commit(source, target, current_user.id)
                flash(
                    f"{counts['promoted']} promoted · {counts['graduated']} graduated · "
                    f"{counts['skipped']} skipped.",
                    "success",
                )
                return redirect(url_for("admin_students.index"))
            preview = student_service.promote_preview(source, target)

    return render_template("admin/students/promote.html", form=form, preview=preview, sessions=sessions)


@bp.route("/export.csv")
@permission_required("students.export")
def export_csv():
    session = current_session()
    rows = student_service.list_students(session_id=session.id if session else None).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Admission No", "First name", "Last name", "Class", "Section", "Roll",
            "Date of birth", "Gender", "Phone", "Status",
        ]
    )
    for student in rows:
        enrollment = student.enrollment_for(session.id) if session else None
        writer.writerow(
            [
                student.admission_no,
                student.first_name,
                student.last_name,
                enrollment.section.school_class.name if enrollment else "",
                enrollment.section.name if enrollment else "",
                enrollment.roll_no if enrollment else "",
                student.dob.isoformat() if student.dob else "",
                student.gender.value if student.gender else "",
                student.phone or "",
                student.status.value,
            ]
        )
    record("students.exported", "Student", None, summary=f"{len(rows)} rows")
    db.session.commit()
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=school-os-students.csv"},
    )
