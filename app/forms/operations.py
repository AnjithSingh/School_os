"""Attendance, timetable and homework forms."""
from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (
    DateField,
    DateTimeLocalField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
    TimeField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from ..models.enums import ChangeType, PeriodKind
from .base import NullableSelect


class AttendanceFilterForm(FlaskForm):
    section_id = SelectField("Section", coerce=int, choices=[], validators=[DataRequired()])
    date = DateField("Date", validators=[DataRequired()])
    submit = SubmitField("Load register")


class PeriodForm(FlaskForm):
    label = StringField("Label", validators=[DataRequired(), Length(max=20)])
    start_time = TimeField("Start time", validators=[DataRequired()])
    end_time = TimeField("End time", validators=[DataRequired()])
    kind = SelectField("Type", choices=PeriodKind.choices(), default="CLASS")
    submit = SubmitField("Save period")


class TimetableCellForm(FlaskForm):
    section_id = SelectField("Section", coerce=int, choices=[], validators=[DataRequired()])
    weekday = SelectField(
        "Day",
        coerce=int,
        choices=[(i, d) for i, d in enumerate(
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        )],
    )
    period_id = SelectField("Period", coerce=int, choices=[], validators=[DataRequired()])
    subject_id = SelectField("Subject", coerce=int, choices=[], validators=[DataRequired()])
    teacher_id = NullableSelect("Teacher", choices=[])
    room = StringField("Room", validators=[Optional(), Length(max=40)])
    submit = SubmitField("Save slot")


class ChangeForm(FlaskForm):
    section_id = SelectField("Section", coerce=int, choices=[], validators=[DataRequired()])
    date = DateField("Date", validators=[DataRequired()])
    change_type = SelectField("Change", choices=ChangeType.choices(), validators=[DataRequired()])
    original_entry_id = NullableSelect("Affected period", choices=[])
    substitute_teacher_id = NullableSelect("Substitute teacher", choices=[])
    new_room = StringField("New room", validators=[Optional(), Length(max=40)])
    reason = StringField("Reason", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Publish change")


class HomeworkForm(FlaskForm):
    section_id = SelectField("Section", coerce=int, choices=[], validators=[DataRequired()])
    subject_id = SelectField("Subject", coerce=int, choices=[], validators=[DataRequired()])
    title = StringField("Title", validators=[DataRequired(), Length(max=160)])
    description = TextAreaField("Instructions", validators=[Optional(), Length(max=4000)])
    assigned_on = DateField("Assigned on", validators=[DataRequired()])
    due_at = DateTimeLocalField("Due by", validators=[Optional()], format="%Y-%m-%dT%H:%M")
    max_marks = IntegerField("Maximum marks", validators=[Optional(), NumberRange(min=1, max=100)])
    attachment = FileField("Attachment")
    submit = SubmitField("Publish homework")


class HomeworkReviewForm(FlaskForm):
    remarks = TextAreaField("Remarks", validators=[Optional(), Length(max=500)])
    marks = IntegerField("Marks", validators=[Optional(), NumberRange(min=0, max=100)])
    submit = SubmitField("Save review")


class StudyMaterialForm(FlaskForm):
    school_class_id = SelectField("Class", coerce=int, choices=[], validators=[DataRequired()])
    section_id = NullableSelect("Section (optional)", choices=[])
    subject_id = SelectField("Subject", coerce=int, choices=[], validators=[DataRequired()])
    title = StringField("Title", validators=[DataRequired(), Length(max=160)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=2000)])
    file = FileField("File")
    submit = SubmitField("Upload material")
