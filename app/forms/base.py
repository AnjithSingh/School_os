"""Shared form helpers."""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import SelectField
from wtforms.validators import Optional


class NullableSelect(SelectField):
    """SelectField where 0 means "not selected" (keeps coerce=int safe)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("coerce", int)
        kwargs.setdefault("validators", [Optional()])
        super().__init__(*args, **kwargs)


class BaseForm(FlaskForm):
    class Meta:
        csrf = True
