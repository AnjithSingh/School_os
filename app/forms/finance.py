"""Fee and finance forms."""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    DecimalField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from ..models.enums import ConcessionType, FeeFrequency, PaymentMethod
from .base import NullableSelect


class FeeCategoryForm(FlaskForm):
    code = StringField("Code", validators=[DataRequired(), Length(max=30)])
    name = StringField("Category name", validators=[DataRequired(), Length(max=100)])
    frequency = SelectField("Frequency", choices=FeeFrequency.choices(), default="ANNUAL")
    description = StringField("Description", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Save category")


class FeeStructureForm(FlaskForm):
    school_class_id = SelectField("Class", coerce=int, choices=[], validators=[DataRequired()])
    fee_category_id = SelectField("Fee category", coerce=int, choices=[], validators=[DataRequired()])
    installment_no = IntegerField("Installment", validators=[DataRequired(), NumberRange(1, 12)], default=1)
    amount = DecimalField("Amount (₹)", validators=[DataRequired(), NumberRange(min=0)], places=2)
    due_date = DateField("Due date", validators=[Optional()])
    submit = SubmitField("Save fee structure")


class PaymentForm(FlaskForm):
    student_fee_id = SelectField("Fee head", coerce=int, choices=[], validators=[DataRequired()])
    amount = DecimalField("Amount received (₹)", validators=[DataRequired(), NumberRange(min=1)], places=2)
    method = SelectField("Payment method", choices=PaymentMethod.choices(), default="CASH")
    reference = StringField("Reference", validators=[Optional(), Length(max=120)])
    notes = StringField("Notes", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Collect payment")


class ConcessionForm(FlaskForm):
    fee_category_id = NullableSelect("Applies to", choices=[])
    concession_type = SelectField("Type", choices=ConcessionType.choices(), default="PERCENT")
    value = IntegerField("Value", validators=[DataRequired(), NumberRange(min=1)])
    reason = StringField("Reason", validators=[DataRequired(), Length(max=255)])
    submit = SubmitField("Request concession")


class FeeGenerateForm(FlaskForm):
    section_id = SelectField("Section", coerce=int, choices=[], validators=[DataRequired()])
    submit = SubmitField("Generate fee records")
