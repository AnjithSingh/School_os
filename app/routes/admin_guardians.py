"""Guardian directory and student-link verification."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..models import Guardian, GuardianStudentLink, Student, User
from ..models.enums import LinkStatus
from ..security.guards import permission_required
from ..services import students as student_service
from ..services.audit import record
from ..utils.pagination import paginate

bp = Blueprint("admin_guardians", __name__, url_prefix="/admin/guardians")


@bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if current_user.scope.value != "STAFF":
        abort(403)


@bp.route("/")
@permission_required("parents.manage")
def index():
    q = request.args.get("q", "").strip()
    query = Guardian.query
    if q:
        needle = f"%{q.lower()}%"
        query = query.filter(
            db.or_(Guardian.full_name.ilike(needle), Guardian.phone.ilike(needle))
        )
    page = paginate(query.order_by(Guardian.full_name), per_page=20)
    pending = GuardianStudentLink.query.filter_by(status=LinkStatus.PENDING).all()
    return render_template("admin/guardians/index.html", page=page, q=q, pending=pending)


@bp.post("/links/<int:link_id>/verify")
@permission_required("guardian.verify")
def verify(link_id: int):
    link = db.get_or_404(GuardianStudentLink, link_id)
    student_service.verify_link(link, current_user.id)
    db.session.commit()
    flash("Guardian link verified.", "success")
    return redirect(url_for("admin_guardians.index"))


@bp.post("/links/<int:link_id>/revoke")
@permission_required("guardian.verify")
def revoke(link_id: int):
    link = db.get_or_404(GuardianStudentLink, link_id)
    student_service.revoke_link(link, current_user.id)
    db.session.commit()
    flash("Guardian access revoked.", "success")
    return redirect(url_for("admin_guardians.index"))


@bp.post("/<int:guardian_id>/toggle-portal")
@permission_required("parents.manage")
def toggle_portal(guardian_id: int):
    guardian = db.get_or_404(Guardian, guardian_id)
    if guardian.user is None:
        flash("This guardian has no portal account yet.", "error")
    else:
        guardian.user.is_active = not guardian.user.is_active
        record("guardian.portal_toggled", "Guardian", guardian.id,
               summary=str(guardian.user.is_active))
        db.session.commit()
        flash("Guardian portal access updated.", "success")
    return redirect(url_for("admin_guardians.index"))
