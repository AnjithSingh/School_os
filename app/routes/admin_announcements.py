"""Announcement management."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..forms.comms import AnnouncementForm
from ..models import Announcement, SchoolClass, Section
from ..models.enums import AnnouncementScope, AnnouncementStatus
from ..models.base import utcnow
from ..security.guards import permission_required
from ..services.audit import record
from ..services.communication import publish_announcement
from ..services.settings import current_session
from ..utils.uploads import UploadError, save_upload
from ..utils.pagination import paginate

bp = Blueprint("admin_announcements", __name__, url_prefix="/admin/announcements")


@bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if current_user.scope.value != "STAFF":
        abort(403)


@bp.route("/", methods=["GET", "POST"])
@permission_required("announcements.manage")
def index():
    session = current_session()
    form = AnnouncementForm()
    form.school_class_id.choices = [(0, "All classes")] + [
        (c.id, c.name) for c in SchoolClass.query.order_by(SchoolClass.display_order)
    ]
    form.section_id.choices = [(0, "All sections")] + [
        (s.id, s.label) for s in Section.query.filter_by(session_id=session.id, is_active=True)
    ] if session else [(0, "All sections")]

    if form.validate_on_submit():
        attachment_id = None
        if form.attachment.data and form.attachment.data.filename:
            try:
                attachment_id = save_upload(
                    form.attachment.data, "announcements", current_user.id
                ).id
            except UploadError as error:
                flash(str(error), "error")

        announcement = Announcement(
            school_id=current_user.school_id,
            session_id=session.id,
            author_id=current_user.id,
            title=form.title.data.strip(),
            body=form.body.data.strip(),
            category=form.category.data,
            audience_scope=form.audience_scope.data,
            school_class_id=form.school_class_id.data or None,
            section_id=form.section_id.data or None,
            publish_at=form.publish_at.data or None,
            expires_at=form.expires_at.data or None,
            is_pinned=form.is_pinned.data,
            attachment_file_id=attachment_id,
            status=AnnouncementStatus.PUBLISHED,
        )
        db.session.add(announcement)
        db.session.flush()
        recipients = publish_announcement(announcement, current_user.id)
        flash(f"Announcement published to {recipients} accounts.", "success")
        return redirect(url_for("admin_announcements.index"))

    page = paginate(
        Announcement.query.filter_by(session_id=session.id)
        .order_by(Announcement.created_at.desc())
        if session
        else Announcement.query.filter(db.false()),
        per_page=20,
    )
    return render_template("admin/announcements/index.html", form=form, page=page)


@bp.post("/<int:announcement_id>/archive")
@permission_required("announcements.manage")
def archive(announcement_id: int):
    announcement = db.get_or_404(Announcement, announcement_id)
    announcement.status = AnnouncementStatus.ARCHIVED
    record("announcement.archived", "Announcement", announcement.id)
    db.session.commit()
    flash("Announcement archived.", "success")
    return redirect(url_for("admin_announcements.index"))
