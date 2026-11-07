"""Authentication forms."""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp


class LoginForm(FlaskForm):
    identifier = StringField(
        "Username or email",
        validators=[DataRequired(message="Enter your username or email."), Length(max=160)],
    )
    password = PasswordField(
        "Password", validators=[DataRequired(message="Enter your password.")]
    )
    remember = BooleanField("Keep me signed in")
    submit = SubmitField("Sign in")


class SetupForm(FlaskForm):
    school_name = StringField(
        "School name", validators=[DataRequired(), Length(min=3, max=160)]
    )
    school_short_name = StringField("Short name", validators=[Optional(), Length(max=60)])
    city = StringField("City", validators=[Optional(), Length(max=80)])
    state = StringField("State", validators=[Optional(), Length(max=80)])
    phone = StringField("School phone", validators=[Optional(), Length(max=30)])
    school_email = StringField("School email", validators=[Optional(), Email(), Length(max=160)])

    admin_name = StringField("Your full name", validators=[DataRequired(), Length(max=120)])
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=40),
            Regexp(r"^[a-zA-Z0-9._-]+$", message="Use letters, numbers, dot, dash or underscore."),
        ],
    )
    email = StringField("Your email", validators=[Optional(), Email(), Length(max=160)])
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=128, message="Use at least 8 characters.")],
    )
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")],
    )
    submit = SubmitField("Create school")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField(
        "New password",
        validators=[DataRequired(), Length(min=8, max=128, message="Use at least 8 characters.")],
    )
    confirm = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords do not match.")],
    )
    submit = SubmitField("Update password")


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "New password",
        validators=[DataRequired(), Length(min=8, max=128, message="Use at least 8 characters.")],
    )
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")],
    )
    submit = SubmitField("Set new password")


class UserForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=40),
            Regexp(r"^[a-zA-Z0-9._-]+$", message="Use letters, numbers, dot, dash or underscore."),
        ],
    )
    email = StringField("Email (optional)", validators=[Optional(), Email(), Length(max=160)])
    phone = StringField("Phone (optional)", validators=[Optional(), Length(max=30)])
    role = SelectField("Role", choices=[], validators=[DataRequired()])
    password = PasswordField(
        "Temporary password",
        validators=[Optional(), Length(min=8, max=128)],
    )
    is_active = BooleanField("Account active", default=True)
    submit = SubmitField("Save user")
