"""Homework oversight for administrators."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..models import Homework, HomeworkSubmission, Section, StudyMaterial
from ..security.guards import permission_required
from ..services.settings import current_session
from ..utils.pagination import paginate

bp = Blueprint("admin_homework", __name__, url_prefix="/admin/homework")


@bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if current_user.scope.value != "STAFF":
        abort(403)


@bp.route("/")
@permission_required("homework.view.all")
def index():
    session = current_session()
    query = Homework.query.filter_by(session_id=session.id).order_by(Homework.assigned_on.desc())
    page = paginate(query, per_page=20)
    sections = Section.query.filter_by(session_id=session.id, is_active=True).all() if session else []
    materials = (
        StudyMaterial.query.filter_by(session_id=session.id)
        .order_by(StudyMaterial.created_at.desc())
        .limit(10)
        .all()
        if session
        else []
    )
    return render_template(
        "admin/homework/index.html", page=page, sections=sections, materials=materials
    )


@bp.route("/<int:homework_id>")
@permission_required("homework.view.all")
def detail(homework_id: int):
    homework = db.get_or_404(Homework, homework_id)
    submissions = {s.student_id: s for s in homework.submissions}
    return render_template(
        "admin/homework/detail.html", homework=homework, submissions=submissions
    )
