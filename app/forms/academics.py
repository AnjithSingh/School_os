"""Academic structure forms."""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from .base import NullableSelect


class SessionForm(FlaskForm):
    name = StringField("Academic year", validators=[DataRequired(), Length(max=20)])
    start_date = DateField("Start date", validators=[DataRequired()])
    end_date = DateField("End date", validators=[DataRequired()])
    is_current = BooleanField("Set as current academic year")
    submit = SubmitField("Save academic year")


class ClassForm(FlaskForm):
    level = IntegerField("Class level", validators=[DataRequired(), NumberRange(min=1, max=12)])
    name = StringField("Display name", validators=[DataRequired(), Length(max=40)])
    submit = SubmitField("Save class")


class SectionForm(FlaskForm):
    school_class_id = SelectField("Class", coerce=int, choices=[], validators=[DataRequired()])
    name = StringField("Section name", validators=[DataRequired(), Length(max=10)])
    room = StringField("Room", validators=[Optional(), Length(max=40)])
    capacity = IntegerField("Capacity", validators=[Optional(), NumberRange(min=1, max=100)], default=45)
    class_teacher_id = NullableSelect("Class teacher", choices=[])
    submit = SubmitField("Save section")


class SubjectForm(FlaskForm):
    code = StringField("Subject code", validators=[DataRequired(), Length(max=20)])
    name = StringField("Subject name", validators=[DataRequired(), Length(max=80)])
    is_elective = BooleanField("Elective subject")
    submit = SubmitField("Save subject")


class ClassSubjectForm(FlaskForm):
    school_class_id = SelectField("Class", coerce=int, choices=[], validators=[DataRequired()])
    subject_id = SelectField("Subject", coerce=int, choices=[], validators=[DataRequired()])
    default_max_marks = IntegerField(
        "Default maximum marks", validators=[Optional(), NumberRange(min=1, max=500)], default=100
    )
    submit = SubmitField("Add subject to class")


class AllocationForm(FlaskForm):
    section_id = SelectField("Section", coerce=int, choices=[], validators=[DataRequired()])
    subject_id = SelectField("Subject", coerce=int, choices=[], validators=[DataRequired()])
    teacher_id = SelectField("Teacher", coerce=int, choices=[], validators=[DataRequired()])
    periods_per_week = IntegerField(
        "Periods per week", validators=[Optional(), NumberRange(min=1, max=20)], default=5
    )
    submit = SubmitField("Assign teacher")
