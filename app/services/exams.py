"""Examination lifecycle: sheets, marks, results and report cards."""
from __future__ import annotations

import json
from datetime import datetime

from ..extensions import db
from ..models import (
    Enrollment,
    ExamRemark,
    Examination,
    ExaminationClass,
    ExaminationSubject,
    MarksAudit,
    MarksEntrySheet,
    MarksRecord,
    ReportCard,
    ResultSummary,
    Section,
    Student,
    SubjectAllocation,
)
from ..models.base import utcnow
from ..models.enums import (
    EnrollmentStatus,
    ExamStatus,
    MarkStatus,
    ReportCardStatus,
    ResultStatus,
    SheetStatus,
)
from .audit import record
from .settings import get_setting


class MarksError(Exception):
    pass


# --------------------------------------------------------------------------
# Sheets
# --------------------------------------------------------------------------
def sections_for(exam: Examination, school_class_id: int) -> list[Section]:
    query = Section.query.filter_by(
        session_id=exam.session_id, school_class_id=school_class_id, is_active=True
    )
    scoped = ExaminationClass.query.filter_by(
        examination_id=exam.id, school_class_id=school_class_id
    ).first()
    if scoped and scoped.section_id:
        query = query.filter(Section.id == scoped.section_id)
    return query.order_by(Section.name).all()


def ensure_sheets(exam: Examination) -> int:
    created = 0
    for exam_subject in exam.subjects:
        for section in sections_for(exam, exam_subject.school_class_id):
            sheet = MarksEntrySheet.query.filter_by(
                examination_subject_id=exam_subject.id, section_id=section.id
            ).first()
            if sheet is not None:
                continue
            allocation = SubjectAllocation.query.filter_by(
                section_id=section.id, subject_id=exam_subject.subject_id
            ).first()
            db.session.add(
                MarksEntrySheet(
                    school_id=exam.school_id,
                    examination_subject_id=exam_subject.id,
                    section_id=section.id,
                    teacher_id=allocation.teacher_id if allocation else None,
                    status=SheetStatus.DRAFT,
                )
            )
            created += 1
    if created:
        db.session.commit()
    return created


def sheet_students(sheet: MarksEntrySheet):
    return (
        Enrollment.query.filter_by(
            section_id=sheet.section_id, session_id=sheet.exam_subject.examination.session_id,
            status=EnrollmentStatus.ACTIVE,
        )
        .join(Enrollment.student)
        .order_by(Enrollment.roll_no.is_(None), Enrollment.roll_no, Enrollment.id)
        .all()
    )


def sheet_rows(sheet: MarksEntrySheet) -> list[dict]:
    records = {r.student_id: r for r in sheet.records}
    rows = []
    for enrollment in sheet_students(sheet):
        rows.append({"enrollment": enrollment, "record": records.get(enrollment.student_id)})
    return rows


def save_marks(
    sheet: MarksEntrySheet,
    entries: dict[int, dict],
    actor_id: int,
    submit: bool = False,
    reason: str | None = None,
) -> dict:
    if sheet.status == SheetStatus.APPROVED:
        raise MarksError("This sheet is approved. Ask the principal to reopen it before editing.")

    max_marks = sheet.exam_subject.max_marks
    existing = {r.student_id: r for r in sheet.records}
    candidates = {e.student_id: e for e in sheet_students(sheet)}
    changed = 0

    for student_id, payload in entries.items():
        enrollment = candidates.get(student_id)
        if enrollment is None:
            continue
        raw_status = (payload.get("status") or "PRESENT").upper()
        try:
            status = MarkStatus(raw_status)
        except ValueError:
            raise MarksError("Unknown marks status.")

        marks = payload.get("marks")
        if status == MarkStatus.PRESENT:
            if marks is None or marks == "":
                raise MarksError(
                    f"Enter marks for every student marked present (roll {enrollment.roll_no})."
                )
            marks = int(marks)
            if marks < 0 or marks > max_marks:
                raise MarksError(f"Marks must be between 0 and {max_marks}.")
        else:
            marks = None

        record_row = existing.get(student_id)
        if record_row is None:
            record_row = MarksRecord(
                school_id=sheet.school_id,
                sheet_id=sheet.id,
                student_id=student_id,
                enrollment_id=enrollment.id,
                marks_obtained=marks,
                status=status,
                remarks=(payload.get("remarks") or "").strip() or None,
                updated_by_id=actor_id,
            )
            db.session.add(record_row)
            changed += 1
            continue

        if record_row.marks_obtained != marks or record_row.status != status:
            db.session.add(
                MarksAudit(
                    school_id=sheet.school_id,
                    marks_record_id=record_row.id,
                    old_marks=record_row.marks_obtained,
                    new_marks=marks,
                    old_status=record_row.status.value,
                    new_status=status.value,
                    reason=(reason or "Marks corrected").strip()[:255],
                    changed_by_id=actor_id,
                    created_at=utcnow(),
                )
            )
            record_row.marks_obtained = marks
            record_row.status = status
            record_row.is_modified = True
            record_row.updated_by_id = actor_id
            changed += 1
        if payload.get("remarks") is not None:
            record_row.remarks = (payload.get("remarks") or "").strip() or None

    if submit:
        sheet.status = SheetStatus.SUBMITTED
        sheet.submitted_at = utcnow()
        record("marks.submitted", "MarksEntrySheet", sheet.id,
               summary=f"{changed} rows changed", actor_id=actor_id)
    else:
        record("marks.saved", "MarksEntrySheet", sheet.id,
               summary=f"{changed} rows changed", actor_id=actor_id)

    db.session.commit()
    return {"changed": changed, "submitted": submit}


def approve_sheet(sheet: MarksEntrySheet, actor_id: int) -> None:
    if sheet.status not in (SheetStatus.SUBMITTED, SheetStatus.REOPENED):
        raise MarksError("Only submitted sheets can be approved.")
    sheet.status = SheetStatus.APPROVED
    sheet.approved_by_id = actor_id
    sheet.approved_at = utcnow()
    record("marks.approved", "MarksEntrySheet", sheet.id, actor_id=actor_id)
    db.session.commit()


def reopen_sheet(sheet: MarksEntrySheet, actor_id: int, reason: str) -> None:
    sheet.status = SheetStatus.REOPENED
    sheet.remarks = reason[:255]
    record("marks.reopened", "MarksEntrySheet", sheet.id, summary=reason, actor_id=actor_id)
    db.session.commit()


def pending_sheets(exam: Examination | None = None):
    query = MarksEntrySheet.query.filter(
        MarksEntrySheet.status.in_([SheetStatus.DRAFT, SheetStatus.REOPENED])
    )
    if exam is not None:
        query = query.join(MarksEntrySheet.exam_subject).filter(
            ExaminationSubject.examination_id == exam.id
        )
    return query


def teacher_sheets(staff_id: int, exam: Examination | None = None):
    query = MarksEntrySheet.query.filter_by(teacher_id=staff_id)
    if exam is not None:
        query = query.join(MarksEntrySheet.exam_subject).filter(
            ExaminationSubject.examination_id == exam.id
        )
    return query.order_by(MarksEntrySheet.id.desc()).all()


# --------------------------------------------------------------------------
# Calculation
# --------------------------------------------------------------------------
def grade_for(percentage: float | None, scale):
    if percentage is None or scale is None:
        return None, None
    rule = scale.rule_for(percentage)
    if rule is None:
        return None, None
    return rule.grade, rule.grade_point


def pass_policy() -> dict:
    return {
        "pass_percent": float(get_setting("result.pass_percent", 33.0)),
        "pass_subject_percent": float(get_setting("result.pass_subject_percent", 33.0)),
        "max_failures": int(get_setting("result.max_failures", 0)),
        "absent_policy": get_setting("attendance.absent_policy", "ZERO"),
    }


def compute_results(exam: Examination, actor_id: int | None = None) -> dict:
    from .academics import classes as all_classes

    policy = pass_policy()
    scale = exam.grading_scale
    class_levels = {c.id: c for c in all_classes(active_only=False)}
    computed = skipped = 0
    incomplete = 0

    exam_subjects = exam.subjects
    seen: set[int] = set()
    for exam_subject in exam_subjects:
        for section in sections_for(exam, exam_subject.school_class_id):
            sheet = MarksEntrySheet.query.filter_by(
                examination_subject_id=exam_subject.id, section_id=section.id
            ).first()
            if sheet is None:
                continue
            if sheet.status != SheetStatus.APPROVED:
                incomplete += 1

    for exam_subject in exam_subjects:
        for section in sections_for(exam, exam_subject.school_class_id):
            enrollments = (
                Enrollment.query.filter_by(
                    section_id=section.id, session_id=exam.session_id,
                    status=EnrollmentStatus.ACTIVE,
                )
                .join(Enrollment.student)
                .all()
            )
            for enrollment in enrollments:
                student = enrollment.student
                if student.id in seen:
                    continue
                seen.add(student.id)
                total_max = total_obtained = 0
                failed = counted = 0
                summary = ResultSummary.query.filter_by(
                    examination_id=exam.id, student_id=student.id
                ).first()
                if summary and summary.section_id not in (None, section.id):
                    continue  # belongs to another section already computed

                for subject_row in exam_subjects:
                    if subject_row.school_class_id != section.school_class_id:
                        continue
                    sheet = MarksEntrySheet.query.filter_by(
                        examination_subject_id=subject_row.id, section_id=section.id
                    ).first()
                    if sheet is None:
                        continue
                    marks = MarksRecord.query.filter_by(
                        sheet_id=sheet.id, student_id=student.id
                    ).first()

                    status = marks.status if marks else MarkStatus.ABSENT
                    obtained = marks.marks_obtained if marks else None

                    if status == MarkStatus.EXEMPT:
                        continue
                    if status == MarkStatus.ABSENT:
                        if policy["absent_policy"] == "EXCLUDED":
                            continue
                        obtained = 0

                    total_max += subject_row.max_marks
                    total_obtained += obtained or 0
                    counted += 1
                    if (obtained or 0) / subject_row.max_marks * 100 < policy["pass_subject_percent"]:
                        failed += 1

                if counted == 0:
                    skipped += 1
                    continue

                percentage = round(total_obtained / total_max * 100, 2)
                grade, grade_point = grade_for(percentage, scale)

                if percentage < policy["pass_percent"] or failed > policy["max_failures"]:
                    status_value = ResultStatus.FAIL
                else:
                    status_value = ResultStatus.PASS

                if summary is None:
                    summary = ResultSummary(
                        school_id=exam.school_id, examination_id=exam.id, student_id=student.id
                    )
                    db.session.add(summary)
                    summary.computed_version = 1
                else:
                    summary.computed_version += 1

                summary.enrollment_id = enrollment.id
                summary.section_id = section.id
                summary.total_max = total_max
                summary.total_obtained = total_obtained
                summary.percentage = percentage
                summary.grade = grade
                summary.grade_point = grade_point
                summary.result_status = status_value
                summary.subjects_failed = failed
                summary.computed_at = utcnow()
                computed += 1

    db.session.flush()
    record("results.computed", "Examination", exam.id,
           summary=f"{computed} results computed", actor_id=actor_id)
    db.session.commit()
    return {"computed": computed, "skipped": skipped, "incomplete_sheets": incomplete}


def subject_breakdown(exam: Examination, student: Student) -> list[dict]:
    enrollment = student.enrollment_for(exam.session_id)
    if enrollment is None:
        return []
    scale = exam.grading_scale
    rows = []
    for exam_subject in exam.subjects:
        if exam_subject.school_class_id != enrollment.section.school_class_id:
            continue
        sheet = MarksEntrySheet.query.filter_by(
            examination_subject_id=exam_subject.id, section_id=enrollment.section_id
        ).first()
        marks = (
            MarksRecord.query.filter_by(sheet_id=sheet.id, student_id=student.id).first()
            if sheet
            else None
        )
        status = marks.status if marks else MarkStatus.ABSENT
        obtained = marks.marks_obtained if marks else None
        percentage = (
            round(obtained / exam_subject.max_marks * 100, 2)
            if obtained is not None
            else None
        )
        grade, _ = grade_for(percentage, scale)
        rows.append(
            {
                "subject": exam_subject.subject,
                "max_marks": exam_subject.max_marks,
                "pass_marks": exam_subject.pass_marks,
                "obtained": obtained,
                "status": status,
                "percentage": percentage,
                "grade": grade,
                "exam_date": exam_subject.exam_date,
                "remarks": marks.remarks if marks else None,
            }
        )
    return rows


# --------------------------------------------------------------------------
# Report cards
# --------------------------------------------------------------------------
def build_snapshot(exam: Examination, student: Student) -> dict:
    from .attendance import student_summary
    from .settings import get_school

    school = get_school()
    enrollment = student.enrollment_for(exam.session_id)
    summary = ResultSummary.query.filter_by(
        examination_id=exam.id, student_id=student.id
    ).first()
    remark = ExamRemark.query.filter_by(
        examination_id=exam.id, student_id=student.id
    ).first()
    attendance = student_summary(student.id, exam.session_id)
    subjects = subject_breakdown(exam, student)

    return {
        "school": {
            "name": school.name if school else "",
            "address": school.address if school else "",
            "phone": school.phone if school else "",
            "email": school.email if school else "",
            "affiliation": school.affiliation_no if school else "",
            "accent": (school.secondary_color if school else "#B7791F"),
        },
        "student": {
            "name": student.full_name,
            "admission_no": student.admission_no,
            "dob": student.dob.isoformat() if student.dob else None,
            "class_section": enrollment.section.label if enrollment else "—",
            "roll_no": enrollment.roll_no if enrollment else None,
        },
        "exam": {
            "name": exam.name,
            "type": exam.exam_type.name if exam.exam_type else "",
            "session": exam.session.name if exam.session else "",
            "result_date": exam.result_date.isoformat() if exam.result_date else None,
        },
        "subjects": [
            {
                "name": row["subject"].name,
                "code": row["subject"].code,
                "max_marks": row["max_marks"],
                "pass_marks": row["pass_marks"],
                "obtained": row["obtained"],
                "status": row["status"].value,
                "grade": row["grade"],
                "remarks": row["remarks"],
            }
            for row in subjects
        ],
        "totals": {
            "max": summary.total_max if summary else 0,
            "obtained": summary.total_obtained if summary else 0,
            "percentage": summary.percentage if summary else 0,
            "grade": summary.grade if summary else None,
            "grade_point": summary.grade_point if summary else None,
            "result": summary.result_status.value if summary else "ABSENT",
            "failed": summary.subjects_failed if summary else 0,
        },
        "attendance": {
            "present": attendance["counts"].get("PRESENT", 0),
            "total": attendance["total"],
            "percentage": attendance["percentage"],
        },
        "remarks": {
            "teacher": remark.teacher_remark if remark else None,
            "principal": remark.principal_remark if remark else None,
        },
        "policy": pass_policy(),
        "generated_at": utcnow().isoformat(),
    }


def generate_report_card(exam: Examination, student: Student, actor_id: int | None = None) -> ReportCard:
    from ..utils.pdf import build_report_card_pdf
    from .files import store_generated_pdf

    summary = ResultSummary.query.filter_by(
        examination_id=exam.id, student_id=student.id
    ).first()
    if summary is None:
        raise MarksError("Compute results before generating report cards.")

    snapshot = build_snapshot(exam, student)
    revision = (
        db.session.query(db.func.max(ReportCard.revision))
        .filter_by(examination_id=exam.id, student_id=student.id)
        .scalar()
        or 0
    ) + 1

    filename = f"report-card-{student.admission_no}-{exam.id}-r{revision}.pdf"
    path = build_report_card_pdf(snapshot, filename)
    stored = store_generated_pdf(path, filename, "report_cards", actor_id)

    card = ReportCard(
        school_id=exam.school_id,
        result_summary_id=summary.id,
        examination_id=exam.id,
        student_id=student.id,
        snapshot_json=json.dumps(snapshot, default=str),
        pdf_file_id=stored.id,
        status=ReportCardStatus.PUBLISHED if exam.status == ExamStatus.PUBLISHED else ReportCardStatus.DRAFT,
        revision=revision,
        generated_by_id=actor_id,
        published_at=utcnow() if exam.status == ExamStatus.PUBLISHED else None,
    )
    db.session.add(card)
    record("reportcard.generated", "ReportCard", card.id,
           summary=f"{student.full_name} revision {revision}", actor_id=actor_id)
    db.session.commit()
    return card


def latest_report_card(exam_id: int, student_id: int) -> ReportCard | None:
    return (
        ReportCard.query.filter_by(examination_id=exam_id, student_id=student_id)
        .order_by(ReportCard.revision.desc())
        .first()
    )


def publish(exam: Examination, actor_id: int) -> None:
    from .communication import notify_user

    exam.status = ExamStatus.PUBLISHED
    exam.published_at = utcnow()
    ReportCard.query.filter_by(examination_id=exam.id).update(
        {"status": ReportCardStatus.PUBLISHED, "published_at": utcnow()}
    )
    record("results.published", "Examination", exam.id,
           summary=exam.name, actor_id=actor_id)
    db.session.commit()

    students = (
        Student.query.join(ResultSummary, ResultSummary.student_id == Student.id)
        .filter(ResultSummary.examination_id == exam.id)
        .all()
    )
    for student in students:
        if student.user_id:
            notify_user(
                user_id=student.user_id,
                kind="RESULT",
                title=f"Results published: {exam.name}",
                body="Your result is now available.",
                link="/student/results",
            )
        from ..models import GuardianStudentLink

        links = GuardianStudentLink.query.filter_by(
            student_id=student.id, can_view_academics=True
        ).all()
        for link in links:
            if link.guardian and link.guardian.user_id and link.guardian.is_verified:
                notify_user(
                    user_id=link.guardian.user_id,
                    kind="RESULT",
                    title=f"Results published: {exam.name}",
                    body=f"{student.full_name}'s result is now available.",
                    link=f"/parent/children/{student.id}/results",
                )
    db.session.commit()
