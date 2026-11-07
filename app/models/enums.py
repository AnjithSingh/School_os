"""Enumerations shared by models, forms, services and templates.

Values are stored as short readable strings so the database stays legible when
inspected with a plain SQLite browser.
"""
from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value

    @classmethod
    def choices(cls):
        return [(member.value, member.value.replace("_", " ").title()) for member in cls]


class Role(StrEnum):
    SUPERUSER = "SUPERUSER"
    PRINCIPAL = "PRINCIPAL"
    ADMIN = "ADMIN"
    ACCOUNTS = "ACCOUNTS"
    ADMISSIONS = "ADMISSIONS"
    TEACHER = "TEACHER"
    SUPPORT = "SUPPORT"
    PARENT = "PARENT"
    STUDENT = "STUDENT"

    @property
    def label(self) -> str:
        return {
            "SUPERUSER": "School Owner",
            "PRINCIPAL": "Principal",
            "ADMIN": "Administrator",
            "ACCOUNTS": "Accounts Staff",
            "ADMISSIONS": "Admissions Staff",
            "TEACHER": "Teacher",
            "SUPPORT": "Support Staff",
            "PARENT": "Parent / Guardian",
            "STUDENT": "Student",
        }[self.value]


STAFF_ROLES = {
    Role.SUPERUSER, Role.PRINCIPAL, Role.ADMIN, Role.ACCOUNTS, Role.ADMISSIONS,
    Role.TEACHER, Role.SUPPORT,
}


class Scope(StrEnum):
    STAFF = "STAFF"
    PARENT = "PARENT"
    STUDENT = "STUDENT"


class Gender(StrEnum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class StaffType(StrEnum):
    TEACHING = "TEACHING"
    ACCOUNTS = "ACCOUNTS"
    ADMISSIONS = "ADMISSIONS"
    ADMIN = "ADMIN"
    SUPPORT = "SUPPORT"


class EmploymentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ON_LEAVE = "ON_LEAVE"
    RESIGNED = "RESIGNED"
    RETIRED = "RETIRED"


class StudentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    TRANSFERRED = "TRANSFERRED"
    ALUMNI = "ALUMNI"


class EnrollmentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PROMOTED = "PROMOTED"
    REPEATED = "REPEATED"
    LEFT = "LEFT"
    TRANSFERRED = "TRANSFERRED"


class LinkStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REVOKED = "REVOKED"


class AttendanceStatus(StrEnum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LATE = "LATE"
    HALF_DAY = "HALF_DAY"
    EXCUSED = "EXCUSED"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()

    @property
    def tone(self) -> str:
        return {
            "PRESENT": "success",
            "ABSENT": "danger",
            "LATE": "warning",
            "HALF_DAY": "info",
            "EXCUSED": "neutral",
        }[self.value]


class TimetableStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class PeriodKind(StrEnum):
    CLASS = "CLASS"
    BREAK = "BREAK"
    LUNCH = "LUNCH"
    ASSEMBLY = "ASSEMBLY"


class ChangeType(StrEnum):
    SUBSTITUTE = "SUBSTITUTE"
    CANCELLED = "CANCELLED"
    ROOM_CHANGE = "ROOM_CHANGE"
    RESCHEDULED = "RESCHEDULED"


class ExamStatus(StrEnum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    MARKS_ENTRY = "MARKS_ENTRY"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"

    @property
    def tone(self) -> str:
        return {
            "DRAFT": "neutral",
            "SCHEDULED": "info",
            "MARKS_ENTRY": "warning",
            "SUBMITTED": "warning",
            "APPROVED": "info",
            "PUBLISHED": "success",
            "ARCHIVED": "neutral",
        }[self.value]


class SheetStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REOPENED = "REOPENED"


class MarkStatus(StrEnum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    EXEMPT = "EXEMPT"


class ResultStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ABSENT = "ABSENT"
    COMPARTMENT = "COMPARTMENT"

    @property
    def tone(self) -> str:
        return {
            "PASS": "success",
            "FAIL": "danger",
            "ABSENT": "warning",
            "COMPARTMENT": "warning",
        }[self.value]


class ReportCardStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    REVISED = "REVISED"


class HomeworkStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CLOSED = "CLOSED"


class SubmissionStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    LATE = "LATE"
    REVIEWED = "REVIEWED"
    RETURNED = "RETURNED"


class FeeFrequency(StrEnum):
    ONE_TIME = "ONE_TIME"
    MONTHLY = "MONTHLY"
    TERM = "TERM"
    ANNUAL = "ANNUAL"


class FeeStatus(StrEnum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    WAIVED = "WAIVED"
    CANCELLED = "CANCELLED"

    @property
    def tone(self) -> str:
        return {
            "PENDING": "warning",
            "PARTIAL": "info",
            "PAID": "success",
            "WAIVED": "neutral",
            "CANCELLED": "neutral",
        }[self.value]


class PaymentMethod(StrEnum):
    CASH = "CASH"
    CHEQUE = "CHEQUE"
    UPI_OFFLINE = "UPI_OFFLINE"
    BANK_TRANSFER = "BANK_TRANSFER"
    MOCK_ONLINE = "MOCK_ONLINE"


class PaymentStatus(StrEnum):
    SUCCESS = "SUCCESS"
    REVERSED = "REVERSED"


class ConcessionType(StrEnum):
    PERCENT = "PERCENT"
    AMOUNT = "AMOUNT"


class ConcessionStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AnnouncementCategory(StrEnum):
    GENERAL = "GENERAL"
    EXAM = "EXAM"
    HOLIDAY = "HOLIDAY"
    TIMETABLE = "TIMETABLE"
    HOMEWORK = "HOMEWORK"
    FEE = "FEE"
    URGENT = "URGENT"


class AnnouncementScope(StrEnum):
    ALL = "ALL"
    STAFF = "STAFF"
    TEACHERS = "TEACHERS"
    PARENTS = "PARENTS"
    STUDENTS = "STUDENTS"
    CLASS = "CLASS"
    SECTION = "SECTION"


class AnnouncementStatus(StrEnum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class LeaveScope(StrEnum):
    STUDENT = "STUDENT"
    STAFF = "STAFF"


class LeaveStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

    @property
    def tone(self) -> str:
        return {
            "PENDING": "warning",
            "APPROVED": "success",
            "REJECTED": "danger",
            "CANCELLED": "neutral",
        }[self.value]


class NotificationKind(StrEnum):
    ANNOUNCEMENT = "ANNOUNCEMENT"
    ATTENDANCE = "ATTENDANCE"
    RESULT = "RESULT"
    FEE = "FEE"
    HOMEWORK = "HOMEWORK"
    TIMETABLE = "TIMETABLE"
    LEAVE = "LEAVE"
    SYSTEM = "SYSTEM"


class DocumentType(StrEnum):
    BIRTH_CERTIFICATE = "BIRTH_CERTIFICATE"
    TRANSFER_CERTIFICATE = "TRANSFER_CERTIFICATE"
    AADHAAR = "AADHAAR"
    MEDICAL = "MEDICAL"
    PHOTO = "PHOTO"
    OTHER = "OTHER"


ROLE_CHOICES = [(r.value, r.label) for r in Role]
