"""Student, guardian and staff forms."""
from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (
    BooleanField,
    DateField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, Regexp

from ..models.enums import Gender, StaffType, StudentStatus
from .base import NullableSelect


class StudentForm(FlaskForm):
    first_name = StringField("First name", validators=[DataRequired(), Length(max=80)])
    last_name = StringField("Last name", validators=[DataRequired(), Length(max=80)])
    admission_no = StringField("Admission number", validators=[Optional(), Length(max=30)])
    dob = DateField("Date of birth", validators=[Optional()])
    gender = SelectField("Gender", choices=[("", "Select")] + Gender.choices())
    class_id = SelectField("Class", coerce=int, choices=[], validators=[DataRequired()])
    section_id = SelectField("Section", coerce=int, choices=[], validators=[DataRequired()])
    roll_no = IntegerField("Roll number", validators=[Optional(), NumberRange(min=1, max=200)])
    admission_date = DateField("Admission date", validators=[Optional()])
    phone = StringField("Phone", validators=[Optional(), Length(max=30)])
    email = StringField("Email", validators=[Optional(), Email(), Length(max=160)])
    address = StringField("Address", validators=[Optional(), Length(max=255)])
    city = StringField("City", validators=[Optional(), Length(max=80)])
    state = StringField("State", validators=[Optional(), Length(max=80)])
    pincode = StringField("PIN code", validators=[Optional(), Length(max=12)])
    emergency_name = StringField("Emergency contact name", validators=[Optional(), Length(max=120)])
    emergency_phone = StringField("Emergency contact phone", validators=[Optional(), Length(max=30)])
    category = StringField("Category", validators=[Optional(), Length(max=40)])
    blood_group = StringField("Blood group", validators=[Optional(), Length(max=8)])
    previous_school = StringField("Previous school", validators=[Optional(), Length(max=200)])
    previous_class = StringField("Previous class", validators=[Optional(), Length(max=40)])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=1000)])
    photo = FileField("Photograph")
    submit = SubmitField("Admit student")


class GuardianForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    relationship = SelectField(
        "Relationship",
        choices=[
            ("Father", "Father"),
            ("Mother", "Mother"),
            ("Guardian", "Guardian"),
            ("Grandparent", "Grandparent"),
            ("Sibling", "Sibling"),
            ("Other", "Other"),
        ],
    )
    phone = StringField("Phone", validators=[Optional(), Length(max=30)])
    email = StringField("Email", validators=[Optional(), Email(), Length(max=160)])
    occupation = StringField("Occupation", validators=[Optional(), Length(max=120)])
    address = StringField("Address", validators=[Optional(), Length(max=255)])
    username = StringField("Portal username", validators=[Optional(), Length(max=40)])
    password = PasswordField("Temporary password", validators=[Optional(), Length(min=8, max=128)])
    is_primary = BooleanField("Primary guardian")
    can_view_academics = BooleanField("View results", default=True)
    can_view_attendance = BooleanField("View attendance", default=True)
    can_pay_fees = BooleanField("View and pay fees", default=True)
    can_apply_leave = BooleanField("Apply for leave", default=True)
    can_view_homework = BooleanField("View homework", default=True)
    receive_notifications = BooleanField("Receive notifications", default=True)
    submit = SubmitField("Save guardian")


class StaffForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    employee_code = StringField("Employee ID", validators=[DataRequired(), Length(max=30)])
    staff_type = SelectField("Staff type", choices=StaffType.choices(), validators=[DataRequired()])
    designation = StringField("Designation", validators=[Optional(), Length(max=80)])
    qualification = StringField("Qualification", validators=[Optional(), Length(max=160)])
    specialisation = StringField("Specialisation", validators=[Optional(), Length(max=160)])
    joining_date = DateField("Joining date", validators=[Optional()])
    employment_status = SelectField(
        "Employment status",
        choices=[
            ("ACTIVE", "Active"),
            ("ON_LEAVE", "On leave"),
            ("RESIGNED", "Resigned"),
            ("RETIRED", "Retired"),
        ],
    )
    gender = SelectField("Gender", choices=[("", "Select")] + Gender.choices())
    dob = DateField("Date of birth", validators=[Optional()])
    phone = StringField("Phone", validators=[Optional(), Length(max=30)])
    email = StringField("Email", validators=[Optional(), Email(), Length(max=160)])
    address = StringField("Address", validators=[Optional(), Length(max=255)])
    username = StringField("Login username", validators=[Optional(), Length(max=40)])
    password = PasswordField("Temporary password", validators=[Optional(), Length(min=8, max=128)])
    submit = SubmitField("Save staff member")


class PromotionForm(FlaskForm):
    from_session_id = SelectField("From academic year", coerce=int, choices=[], validators=[DataRequired()])
    to_session_id = SelectField("To academic year", coerce=int, choices=[], validators=[DataRequired()])
    confirm = BooleanField("I have reviewed the promotion preview")
    submit = SubmitField("Promote students")


class StudentStatusForm(FlaskForm):
    status = SelectField("Student status", choices=StudentStatus.choices())
    submit = SubmitField("Update status")
