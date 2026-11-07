"""School profile and academic policy forms."""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, FloatField, IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional


class SchoolProfileForm(FlaskForm):
    name = StringField("School name", validators=[DataRequired(), Length(max=160)])
    short_name = StringField("Short name", validators=[Optional(), Length(max=60)])
    address_line1 = StringField("Address", validators=[Optional(), Length(max=200)])
    city = StringField("City", validators=[Optional(), Length(max=80)])
    state = StringField("State", validators=[Optional(), Length(max=80)])
    pincode = StringField("PIN code", validators=[Optional(), Length(max=12)])
    phone = StringField("Phone", validators=[Optional(), Length(max=30)])
    email = StringField("Email", validators=[Optional(), Email(), Length(max=160)])
    website = StringField("Website", validators=[Optional(), Length(max=200)])
    principal_name = StringField("Principal name", validators=[Optional(), Length(max=120)])
    affiliation_no = StringField("Affiliation number", validators=[Optional(), Length(max=80)])
    motto = StringField("Motto", validators=[Optional(), Length(max=200)])
    primary_color = StringField("Primary colour", validators=[Optional(), Length(max=9)])
    secondary_color = StringField("Secondary colour", validators=[Optional(), Length(max=9)])
    save_profile = SubmitField("Save profile")


class AcademicPolicyForm(FlaskForm):
    pass_percent = FloatField(
        "Overall pass percentage", validators=[DataRequired(), NumberRange(0, 100)]
    )
    pass_subject_percent = FloatField(
        "Per-subject pass percentage", validators=[DataRequired(), NumberRange(0, 100)]
    )
    max_failures = IntegerField(
        "Allowed subject failures", validators=[DataRequired(), NumberRange(0, 5)]
    )
    absent_policy = SelectField(
        "Absent subject treatment",
        choices=[
            ("ZERO", "Count as zero in totals"),
            ("EXCLUDED", "Exclude from totals"),
        ],
    )
    save_policy = SubmitField("Save policy")
