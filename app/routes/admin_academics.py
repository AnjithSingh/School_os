"""Classes, sections, subjects, allocations and grading."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..forms.academics import (
    AllocationForm,
    ClassForm,
    ClassSubjectForm,
    SectionForm,
    SubjectForm,
)
from ..forms.exams import GradeScaleForm
from ..models import (
    ClassSubject,
    GradeRule,
    GradeScale,
    SchoolClass,
    Section,
    Subject,
    SubjectAllocation,
)
from ..models.enums import EnrollmentStatus
from ..security.guards import permission_required
from ..services import academics
from ..services.audit import record
from ..services.settings import current_session

bp = Blueprint("admin_academics", __name__, url_prefix="/admin/academics")


@bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if current_user.scope.value != "STAFF":
        abort(403)


@bp.route("/")
@permission_required("academics.manage")
def index():
    session = current_session()
    classes = SchoolClass.query.order_by(SchoolClass.display_order).all()
    sections = academics.sections_for(session.id) if session else []
    subjects = Subject.query.order_by(Subject.display_order, Subject.name).all()
    allocations = (
        SubjectAllocation.query.filter_by(session_id=session.id)
        .join(SubjectAllocation.section)
        .order_by(Section.school_class_id, Section.name)
        .all()
        if session
        else []
    )
    offerings = ClassSubject.query.filter_by(session_id=session.id).all() if session else []

    class_form = ClassForm()
    section_form = SectionForm()
    section_form.school_class_id.choices = [(c.id, c.name) for c in classes]
    section_form.class_teacher_id.choices = [(0, "No class teacher")] + [
        (int(value), label) for value, label in academics.teacher_options(include_empty=False)
    ]
    subject_form = SubjectForm()
    offering_form = ClassSubjectForm()
    offering_form.school_class_id.choices = [(c.id, c.name) for c in classes]
    offering_form.subject_id.choices = [(s.id, f"{s.name} ({s.code})") for s in subjects]
    allocation_form = AllocationForm()
    allocation_form.section_id.choices = [(s.id, s.label) for s in sections]
    allocation_form.subject_id.choices = [(s.id, s.name) for s in subjects]
    allocation_form.teacher_id.choices = [
        (int(value), label) for value, label in academics.teacher_options(include_empty=False)
    ]

    return render_template(
        "admin/academics/index.html",
        session=session,
        classes=classes,
        sections=sections,
        subjects=subjects,
        allocations=allocations,
        offerings=offerings,
        class_form=class_form,
        section_form=section_form,
        subject_form=subject_form,
        offering_form=offering_form,
        allocation_form=allocation_form,
    )


@bp.post("/classes")
@permission_required("academics.manage")
def create_class():
    form = ClassForm()
    if form.validate_on_submit():
        if SchoolClass.query.filter_by(level=form.level.data).first():
            flash("A class with that level already exists.", "error")
        else:
            db.session.add(
                SchoolClass(
                    school_id=current_user.school_id,
                    level=form.level.data,
                    name=form.name.data.strip(),
                    display_order=form.level.data,
                )
            )
            record("class.created", "SchoolClass", None, summary=form.name.data)
            db.session.commit()
            flash("Class created.", "success")
    else:
        flash("Please check the class details.", "error")
    return redirect(url_for("admin_academics.index"))


@bp.post("/sections")
@permission_required("academics.manage")
def create_section():
    session = current_session()
    form = SectionForm()
    form.school_class_id.choices = [
        (c.id, c.name) for c in SchoolClass.query.order_by(SchoolClass.display_order)
    ]
    form.class_teacher_id.choices = [(0, "No class teacher")] + [
        (int(value), label) for value, label in academics.teacher_options(include_empty=False)
    ]
    if session is None:
        flash("Create an academic year first.", "error")
        return redirect(url_for("admin_academics.index"))
    if form.validate_on_submit():
        exists = Section.query.filter_by(
            session_id=session.id,
            school_class_id=form.school_class_id.data,
            name=form.name.data.strip().upper(),
        ).first()
        if exists:
            flash("That section already exists for this class.", "error")
        else:
            db.session.add(
                Section(
                    school_id=current_user.school_id,
                    session_id=session.id,
                    school_class_id=form.school_class_id.data,
                    name=form.name.data.strip().upper(),
                    room=form.room.data,
                    capacity=form.capacity.data or 45,
                    class_teacher_id=form.class_teacher_id.data or None,
                )
            )
            record("section.created", "Section", None, summary=form.name.data)
            db.session.commit()
            flash("Section created.", "success")
    else:
        flash("Please check the section details.", "error")
    return redirect(url_for("admin_academics.index"))


@bp.post("/subjects")
@permission_required("academics.manage")
def create_subject():
    form = SubjectForm()
    if form.validate_on_submit():
        if Subject.query.filter_by(code=form.code.data.strip().upper()).first():
            flash("That subject code already exists.", "error")
        else:
            db.session.add(
                Subject(
                    school_id=current_user.school_id,
                    code=form.code.data.strip().upper(),
                    name=form.name.data.strip(),
                    is_elective=form.is_elective.data,
                )
            )
            record("subject.created", "Subject", None, summary=form.name.data)
            db.session.commit()
            flash("Subject created.", "success")
    else:
        flash("Please check the subject details.", "error")
    return redirect(url_for("admin_academics.index"))


@bp.post("/offerings")
@permission_required("academics.manage")
def add_offering():
    session = current_session()
    form = ClassSubjectForm()
    form.school_class_id.choices = [(c.id, c.name) for c in SchoolClass.query.all()]
    form.subject_id.choices = [(s.id, s.name) for s in Subject.query.all()]
    if session is None or not form.validate_on_submit():
        flash("Please check the class subject details.", "error")
        return redirect(url_for("admin_academics.index"))
    exists = ClassSubject.query.filter_by(
        session_id=session.id,
        school_class_id=form.school_class_id.data,
        subject_id=form.subject_id.data,
    ).first()
    if exists:
        flash("That subject is already offered to the class.", "error")
    else:
        db.session.add(
            ClassSubject(
                school_id=current_user.school_id,
                session_id=session.id,
                school_class_id=form.school_class_id.data,
                subject_id=form.subject_id.data,
                default_max_marks=form.default_max_marks.data or 100,
            )
        )
        db.session.commit()
        flash("Subject added to class.", "success")
    return redirect(url_for("admin_academics.index"))


@bp.post("/allocations")
@permission_required("academics.manage")
def create_allocation():
    session = current_session()
    form = AllocationForm()
    form.section_id.choices = [(s.id, s.label) for s in academics.sections_for(session.id)] if session else []
    form.subject_id.choices = [(s.id, s.name) for s in Subject.query.all()]
    form.teacher_id.choices = [
        (int(value), label) for value, label in academics.teacher_options(include_empty=False)
    ]
    if session is None or not form.validate_on_submit():
        flash("Please check the allocation details.", "error")
        return redirect(url_for("admin_academics.index"))

    exists = SubjectAllocation.query.filter_by(
        section_id=form.section_id.data, subject_id=form.subject_id.data
    ).first()
    if exists:
        exists.teacher_id = form.teacher_id.data
        exists.periods_per_week = form.periods_per_week.data or 5
        flash("Allocation updated.", "success")
    else:
        db.session.add(
            SubjectAllocation(
                school_id=current_user.school_id,
                session_id=session.id,
                section_id=form.section_id.data,
                subject_id=form.subject_id.data,
                teacher_id=form.teacher_id.data,
                periods_per_week=form.periods_per_week.data or 5,
            )
        )
        flash("Teacher assigned.", "success")
    record("allocation.saved", "SubjectAllocation", None)
    db.session.commit()
    return redirect(url_for("admin_academics.index"))


@bp.route("/grading", methods=["GET", "POST"])
@permission_required("academics.manage")
def grading():
    scale = GradeScale.query.filter_by(is_default=True).first()
    if scale is None:
        flash("No grading scale is configured.", "error")
        return redirect(url_for("admin_academics.index"))

    form = GradeScaleForm(obj=scale)
    if request.method == "GET":
        form.rules.min_entries = 0
        while len(form.rules):
            form.rules.pop_entry()
        form.rules.min_entries = 1
        for rule in scale.rules:
            form.rules.append_entry(
                {
                    "grade": rule.grade,
                    "min_percent": rule.min_percent,
                    "max_percent": rule.max_percent,
                    "grade_point": rule.grade_point,
                    "description": rule.description,
                }
            )

    if form.validate_on_submit():
        scale.name = form.name.data.strip()
        GradeRule.query.filter_by(grade_scale_id=scale.id).delete()
        for row in form.rules.data:
            db.session.add(
                GradeRule(
                    school_id=scale.school_id,
                    grade_scale_id=scale.id,
                    grade=row["grade"].strip(),
                    min_percent=row["min_percent"],
                    max_percent=row["max_percent"],
                    grade_point=row.get("grade_point"),
                    description=row.get("description"),
                )
            )
        record("grading.updated", "GradeScale", scale.id)
        db.session.commit()
        flash("Grading scale updated.", "success")
        return redirect(url_for("admin_academics.grading"))

    return render_template("admin/academics/grading.html", form=form, scale=scale)
