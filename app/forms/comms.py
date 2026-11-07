"""Announcement and leave forms."""
from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (
    BooleanField,
    DateField,
    DateTimeLocalField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, Optional

from ..models.enums import AnnouncementCategory, AnnouncementScope
from .base import NullableSelect


class AnnouncementForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=160)])
    body = TextAreaField("Message", validators=[DataRequired(), Length(max=5000)])
    category = SelectField("Category", choices=AnnouncementCategory.choices(), default="GENERAL")
    audience_scope = SelectField("Audience", choices=AnnouncementScope.choices(), default="ALL")
    school_class_id = NullableSelect("Class (for class audience)", choices=[])
    section_id = NullableSelect("Section (optional)", choices=[])
    publish_at = DateTimeLocalField("Publish at", validators=[Optional()], format="%Y-%m-%dT%H:%M")
    expires_at = DateTimeLocalField("Expires at", validators=[Optional()], format="%Y-%m-%dT%H:%M")
    is_pinned = BooleanField("Pin to top")
    attachment = FileField("Attachment")
    submit = SubmitField("Publish announcement")


class LeaveForm(FlaskForm):
    student_id = NullableSelect("Student", choices=[])
    from_date = DateField("From", validators=[DataRequired()])
    to_date = DateField("To", validators=[DataRequired()])
    leave_type = SelectField(
        "Type",
        choices=[("SICK", "Sick leave"), ("FAMILY", "Family function"), ("OTHER", "Other")],
    )
    reason = TextAreaField("Reason", validators=[DataRequired(), Length(max=1000)])
    attachment = FileField("Supporting document")
    submit = SubmitField("Submit application")


class LeaveReviewForm(FlaskForm):
    decision = SelectField("Decision", choices=[("APPROVED", "Approve"), ("REJECTED", "Reject")])
    remarks = StringField("Remarks", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Save decision")
