"""Model registry.

Importing every model module here guarantees that Alembic autogenerate and
``db.create_all()`` see the complete metadata.
"""
from .academics import ClassSubject, SchoolClass, Section, Subject, SubjectAllocation, WorkingDay
from .attendance import AttendanceRecord
from .base import SoftDeleteMixin, TenantMixin, TimestampMixin, enum_column, utcnow
from .communication import Announcement, AnnouncementAudience, LeaveApplication, Notification
from .enums import *  # noqa: F401,F403
from .examination import (
    ExamRemark,
    ExamType,
    Examination,
    ExaminationClass,
    ExaminationSubject,
    GradeRule,
    GradeScale,
    MarksAudit,
    MarksEntrySheet,
    MarksRecord,
    ReportCard,
    ResultSummary,
)
from .finance import (
    FeeCategory,
    FeeConcession,
    FeePayment,
    FeeStructure,
    ReceiptCounter,
    StudentFee,
)
from .homework import Homework, HomeworkSubmission, StudyMaterial
from .identity import (
    AcademicSession,
    AppSetting,
    AuditLog,
    Holiday,
    LoginAttempt,
    PasswordResetToken,
    School,
    StoredFile,
    User,
)
from .people import (
    Enrollment,
    Guardian,
    GuardianStudentLink,
    StaffProfile,
    Student,
    StudentDocument,
)
from .timetable import Timetable, TimetableChange, TimetableEntry, TimetablePeriod

__all__ = [
    "AcademicSession",
    "Announcement",
    "AnnouncementAudience",
    "AppSetting",
    "AttendanceRecord",
    "AuditLog",
    "ClassSubject",
    "Enrollment",
    "ExamRemark",
    "ExamType",
    "Examination",
    "ExaminationClass",
    "ExaminationSubject",
    "FeeCategory",
    "FeeConcession",
    "FeePayment",
    "FeeStructure",
    "GradeRule",
    "GradeScale",
    "Guardian",
    "GuardianStudentLink",
    "Holiday",
    "Homework",
    "HomeworkSubmission",
    "LeaveApplication",
    "LoginAttempt",
    "MarksAudit",
    "MarksEntrySheet",
    "MarksRecord",
    "Notification",
    "PasswordResetToken",
    "ReceiptCounter",
    "ReportCard",
    "ResultSummary",
    "School",
    "SchoolClass",
    "Section",
    "StaffProfile",
    "StoredFile",
    "Student",
    "StudentDocument",
    "StudentFee",
    "StudyMaterial",
    "Subject",
    "SubjectAllocation",
    "Timetable",
    "TimetableChange",
    "TimetableEntry",
    "TimetablePeriod",
    "User",
    "WorkingDay",
    "utcnow",
]
