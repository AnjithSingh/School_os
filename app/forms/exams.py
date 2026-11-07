"""Examination forms."""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    FieldList,
    FloatField,
    FormField,
    IntegerField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
    TimeField,
    Form as WTForm,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from .base import NullableSelect


class ExamForm(FlaskForm):
    exam_type_id = SelectField("Examination type", coerce=int, choices=[], validators=[DataRequired()])
    name = StringField("Examination name", validators=[DataRequired(), Length(max=120)])
    start_date = DateField("Start date", validators=[Optional()])
    end_date = DateField("End date", validators=[Optional()])
    result_date = DateField("Result publication date", validators=[Optional()])
    grading_scale_id = NullableSelect("Grading scale", choices=[])
    instructions = TextAreaField("Instructions", validators=[Optional(), Length(max=2000)])
    class_ids = SelectMultipleField("Applicable classes", coerce=int, choices=[])
    pass_percent = FloatField("Overall pass percentage", validators=[Optional(), NumberRange(0, 100)])
    pass_subject_percent = FloatField(
        "Per-subject pass percentage", validators=[Optional(), NumberRange(0, 100)]
    )
    submit = SubmitField("Save examination")


class ExamSubjectForm(FlaskForm):
    school_class_id = SelectField("Class", coerce=int, choices=[], validators=[DataRequired()])
    subject_id = SelectField("Subject", coerce=int, choices=[], validators=[DataRequired()])
    exam_date = DateField("Exam date", validators=[Optional()])
    start_time = TimeField("Start time", validators=[Optional()])
    end_time = TimeField("End time", validators=[Optional()])
    room = StringField("Room", validators=[Optional(), Length(max=40)])
    max_marks = IntegerField("Maximum marks", validators=[DataRequired(), NumberRange(1, 500)], default=100)
    pass_marks = IntegerField("Passing marks", validators=[DataRequired(), NumberRange(0, 500)], default=33)
    submit = SubmitField("Add subject")


class RemarkForm(FlaskForm):
    teacher_remark = TextAreaField("Teacher remark", validators=[Optional(), Length(max=400)])
    principal_remark = TextAreaField("Principal remark", validators=[Optional(), Length(max=400)])
    submit = SubmitField("Save remarks")


class GradeRuleRow(WTForm):
    grade = StringField("Grade", validators=[DataRequired(), Length(max=8)])
    min_percent = FloatField("From %", validators=[DataRequired(), NumberRange(0, 100)])
    max_percent = FloatField("To %", validators=[DataRequired(), NumberRange(0, 100)])
    grade_point = FloatField("Points", validators=[Optional(), NumberRange(0, 10)])
    description = StringField("Description", validators=[Optional(), Length(max=120)])


class GradeScaleForm(FlaskForm):
    name = StringField("Scale name", validators=[DataRequired(), Length(max=80)])
    rules = FieldList(FormField(GradeRuleRow), min_entries=1)
    submit = SubmitField("Save grading scale")
