"""Fee configuration, collection, receipts and concessions."""
from __future__ import annotations

import os
from datetime import date

from flask import (
    Blueprint,
    abort,
    after_this_request,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user

from ..extensions import db
from ..forms.finance import (
    ConcessionForm,
    FeeCategoryForm,
    FeeGenerateForm,
    FeeStructureForm,
    PaymentForm,
)
from ..models import (
    Enrollment,
    FeeCategory,
    FeeConcession,
    FeePayment,
    FeeStructure,
    Section,
    Student,
    StudentFee,
)
from ..models.base import utcnow
from ..models.enums import ConcessionStatus, ConcessionType, FeeStatus, PaymentStatus
from ..security.guards import permission_required
from ..services import academics
from ..services import fees as fee_service
from ..services.audit import record
from ..services.settings import current_session
from ..utils.money import to_paise
from ..utils.pagination import paginate
from ..utils.pdf import build_receipt_pdf

bp = Blueprint("admin_fees", __name__, url_prefix="/admin/fees")


@bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if current_user.scope.value != "STAFF":
        abort(403)


@bp.route("/")
@permission_required("fees.view.all")
def index():
    session = current_session()
    if session is None:
        flash("Create an academic year first.", "error")
        return redirect(url_for("admin.dashboard"))

    finance = fee_service.collection_summary(session.id)
    categories = fee_service.categories(session.id)
    structures = (
        FeeStructure.query.filter_by(session_id=session.id)
        .join(FeeStructure.category)
        .order_by(FeeCategory.name, FeeStructure.installment_no)
        .all()
    )
    dues = (
        StudentFee.query.filter(
            StudentFee.session_id == session.id,
            StudentFee.status.in_([FeeStatus.PENDING, FeeStatus.PARTIAL]),
        )
        .order_by(StudentFee.due_date)
        .limit(12)
        .all()
    )
    classes = academics.classes()
    sections = Section.query.filter_by(session_id=session.id, is_active=True).all()

    category_form = FeeCategoryForm()
    structure_form = FeeStructureForm()
    structure_form.school_class_id.choices = [(c.id, c.name) for c in classes]
    structure_form.fee_category_id.choices = [(c.id, c.name) for c in categories]
    generate_form = FeeGenerateForm()
    generate_form.section_id.choices = [(s.id, s.label) for s in sections]

    return render_template(
        "admin/fees/index.html",
        session=session,
        finance=finance,
        categories=categories,
        structures=structures,
        dues=dues,
        category_form=category_form,
        structure_form=structure_form,
        generate_form=generate_form,
        sections=sections,
        classes=classes,
    )


@bp.post("/categories")
@permission_required("fees.manage")
def create_category():
    session = current_session()
    form = FeeCategoryForm()
    if form.validate_on_submit():
        if FeeCategory.query.filter_by(session_id=session.id, code=form.code.data.upper()).first():
            flash("That fee code already exists.", "error")
        else:
            db.session.add(
                FeeCategory(
                    school_id=current_user.school_id,
                    session_id=session.id,
                    code=form.code.data.strip().upper(),
                    name=form.name.data.strip(),
                    frequency=form.frequency.data,
                    description=form.description.data,
                )
            )
            db.session.commit()
            flash("Fee category created.", "success")
    else:
        flash("Please check the category details.", "error")
    return redirect(url_for("admin_fees.index"))


@bp.post("/structures")
@permission_required("fees.manage")
def create_structure():
    session = current_session()
    form = FeeStructureForm()
    form.school_class_id.choices = [(c.id, c.name) for c in academics.classes()]
    form.fee_category_id.choices = [(c.id, c.name) for c in fee_service.categories(session.id)]
    if not form.validate_on_submit():
        flash("Please check the fee structure details.", "error")
        return redirect(url_for("admin_fees.index"))

    exists = FeeStructure.query.filter_by(
        session_id=session.id,
        school_class_id=form.school_class_id.data,
        fee_category_id=form.fee_category_id.data,
        installment_no=form.installment_no.data,
    ).first()
    if exists:
        exists.amount_paise = to_paise(form.amount.data)
        exists.due_date = form.due_date.data
        flash("Fee structure updated.", "success")
    else:
        db.session.add(
            FeeStructure(
                school_id=current_user.school_id,
                session_id=session.id,
                school_class_id=form.school_class_id.data,
                fee_category_id=form.fee_category_id.data,
                installment_no=form.installment_no.data,
                amount_paise=to_paise(form.amount.data),
                due_date=form.due_date.data,
            )
        )
        flash("Fee structure created.", "success")
    record("fees.structure_saved", "FeeStructure", None)
    db.session.commit()
    return redirect(url_for("admin_fees.index"))


@bp.post("/generate")
@permission_required("fees.manage")
def generate():
    session = current_session()
    form = FeeGenerateForm()
    form.section_id.choices = [
        (s.id, s.label) for s in Section.query.filter_by(session_id=session.id)
    ]
    if form.validate_on_submit():
        created = fee_service.generate_for_section(
            session.id, form.section_id.data, current_user.id
        )
        flash(f"{created} student fee records generated.", "success" if created else "info")
    else:
        flash("Choose a section to generate fees for.", "error")
    return redirect(url_for("admin_fees.index"))


@bp.route("/student/<int:student_id>")
@permission_required("fees.view.all")
def student_ledger(student_id: int):
    session = current_session()
    student = db.get_or_404(Student, student_id)
    ledger = fee_service.student_ledger(student.id, session.id)
    payable = [row for row in ledger["rows"] if row.balance_paise > 0]

    form = PaymentForm()
    form.student_fee_id.choices = [
        (
            row.id,
            f"{row.fee_structure.category.name} · #{row.fee_structure.installment_no} · "
            f"balance {row.balance_paise / 100:.2f}",
        )
        for row in payable
    ]
    if payable:
        form.amount.data = payable[0].balance_paise / 100

    return render_template(
        "admin/fees/ledger.html",
        student=student,
        ledger=ledger,
        form=form,
        payable=payable,
        concessions=FeeConcession.query.filter_by(
            student_id=student.id, session_id=session.id
        ).all(),
    )


@bp.post("/student/<int:student_id>/pay")
@permission_required("fees.collect")
def collect(student_id: int):
    session = current_session()
    student = db.get_or_404(Student, student_id)
    form = PaymentForm()
    rows = StudentFee.query.filter_by(student_id=student.id, session_id=session.id).all()
    form.student_fee_id.choices = [(r.id, r.fee_structure.category.name) for r in rows]
    if form.validate_on_submit():
        student_fee = db.session.get(StudentFee, form.student_fee_id.data)
        if student_fee is None or student_fee.student_id != student.id:
            abort(404)
        try:
            payment = fee_service.record_payment(
                student_fee=student_fee,
                amount_paise=to_paise(form.amount.data),
                method=form.method.data,
                actor_id=current_user.id,
                reference=form.reference.data,
                notes=form.notes.data,
            )
            flash(f"Payment recorded. Receipt {payment.receipt_no}.", "success")
            return redirect(url_for("admin_fees.receipt", payment_id=payment.id))
        except fee_service.FeeError as error:
            db.session.rollback()
            flash(str(error), "error")
    else:
        flash("Please check the payment details.", "error")
    return redirect(url_for("admin_fees.student_ledger", student_id=student.id))


@bp.route("/payments")
@permission_required("fees.view.all")
def payments():
    session = current_session()
    query = FeePayment.query.filter_by(session_id=session.id).order_by(
        FeePayment.paid_at.desc()
    )
    page = paginate(query, per_page=30)
    return render_template("admin/fees/payments.html", page=page)


@bp.route("/receipt/<int:payment_id>.pdf")
@permission_required("fees.view.all")
def receipt(payment_id: int):
    payment = db.get_or_404(FeePayment, payment_id)
    context = fee_service.receipt_context(payment)
    path = build_receipt_pdf(context, f"receipt-{payment.receipt_no}.pdf")

    @after_this_request
    def _cleanup(response):
        try:
            os.unlink(path)
        except OSError:
            pass
        return response

    return send_file(
        path, mimetype="application/pdf", as_attachment=True,
        download_name=f"receipt-{payment.receipt_no}.pdf",
    )


@bp.post("/payments/<int:payment_id>/reverse")
@permission_required("fees.collect")
def reverse(payment_id: int):
    payment = db.get_or_404(FeePayment, payment_id)
    reason = request.form.get("reason", "").strip()
    if not reason:
        flash("A reason is required to reverse a payment.", "error")
    else:
        try:
            fee_service.reverse_payment(payment, reason, current_user.id)
            flash("Payment reversed. The ledger has been updated.", "success")
        except fee_service.FeeError as error:
            flash(str(error), "error")
    return redirect(url_for("admin_fees.payments"))


@bp.post("/concessions/<int:student_id>")
@permission_required("fees.concessions")
def add_concession(student_id: int):
    session = current_session()
    student = db.get_or_404(Student, student_id)
    form = ConcessionForm()
    form.fee_category_id.choices = [(0, "All categories")] + [
        (c.id, c.name) for c in fee_service.categories(session.id)
    ]
    if form.validate_on_submit():
        db.session.add(
            FeeConcession(
                school_id=current_user.school_id,
                student_id=student.id,
                session_id=session.id,
                fee_category_id=form.fee_category_id.data or None,
                concession_type=ConcessionType(form.concession_type.data),
                value=form.value.data,
                reason=form.reason.data,
                status=ConcessionStatus.APPROVED,
                approved_by_id=current_user.id,
                approved_at=utcnow(),
            )
        )
        db.session.commit()
        fee_service.regenerate_concession(student.id, session.id, current_user.id)
        flash("Concession approved and applied to unpaid fees.", "success")
    else:
        flash("Please check the concession details.", "error")
    return redirect(url_for("admin_fees.student_ledger", student_id=student.id))
