"""Small builders shared by the test modules."""
from __future__ import annotations

from app.extensions import db
from app.models import (
    Examination,
    ExaminationSubject,
    MarksEntrySheet,
)
from app.models.enums import ExamStatus
from app.services.exams import ensure_sheets


def login(client, identifier, password, endpoint="/login"):
    """Sign in through the real form so session scope is set correctly."""
    return client.post(
        endpoint,
        data={"identifier": identifier, "password": password},
        follow_redirects=False,
    )


def make_exam(demo, *, name="FA1 2026", status=ExamStatus.MARKS_ENTRY, subjects=("maths",)):
    exam = Examination(
        school_id=demo["school"].id,
        session_id=demo["session"].id,
        exam_type_id=demo["exam_type"].id,
        name=name,
        status=status,
        grading_scale_id=demo["grade_scale"].id,
    )
    db.session.add(exam)
    db.session.flush()

    for key in subjects:
        subject = demo["subjects"][key]
        db.session.add(
            ExaminationSubject(
                school_id=demo["school"].id,
                examination_id=exam.id,
                school_class_id=demo["school_class"].id,
                subject_id=subject.id,
                max_marks=100,
                pass_marks=33,
            )
        )
    db.session.commit()
    ensure_sheets(exam)
    return exam


def sheet_for(exam, section, subject_id):
    return (
        MarksEntrySheet.query.join(MarksEntrySheet.exam_subject)
        .filter(
            MarksEntrySheet.section_id == section.id,
            ExaminationSubject.examination_id == exam.id,
            ExaminationSubject.subject_id == subject_id,
        )
        .one()
    )
