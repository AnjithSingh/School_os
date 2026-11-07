"""Announcements, notifications and audience resolution."""
from __future__ import annotations

from sqlalchemy import and_, or_

from ..extensions import db
from ..models import (
    Announcement,
    Enrollment,
    GuardianStudentLink,
    Notification,
    Section,
    Student,
    User,
)
from ..models.base import utcnow
from ..models.enums import (
    AnnouncementScope,
    AnnouncementStatus,
    EnrollmentStatus,
    NotificationKind,
    Role,
)
from .audit import record


def notify_user(
    *,
    user_id: int,
    kind: NotificationKind | str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    school_id: int | None = None,
) -> Notification | None:
    if not user_id:
        return None
    try:
        kind_value = kind if isinstance(kind, NotificationKind) else NotificationKind(kind)
    except ValueError:
        kind_value = NotificationKind.SYSTEM
    if school_id is None:
        user = db.session.get(User, user_id)
        if user is None:
            return None
        school_id = user.school_id
    notification = Notification(
        school_id=school_id,
        user_id=user_id,
        kind=kind_value,
        title=title[:160],
        body=(body or "")[:400] or None,
        link_url=link,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.session.add(notification)
    return notification


def notification_recipients(announcement: Announcement) -> list[int]:
    scope = announcement.audience_scope
    session_id = announcement.session_id
    ids: set[int] = set()

    def add_users(role: Role):
        rows = User.query.filter_by(role=role, is_active=True).all()
        ids.update(user.id for user in rows)

    if scope == AnnouncementScope.ALL:
        for role in Role:
            add_users(role)
    elif scope == AnnouncementScope.STAFF:
        for role in (Role.SUPERUSER, Role.PRINCIPAL, Role.ADMIN, Role.ACCOUNTS,
                     Role.ADMISSIONS, Role.TEACHER):
            add_users(role)
    elif scope == AnnouncementScope.TEACHERS:
        add_users(Role.TEACHER)
    elif scope == AnnouncementScope.PARENTS:
        add_users(Role.PARENT)
    elif scope == AnnouncementScope.STUDENTS:
        add_users(Role.STUDENT)
    elif scope in (AnnouncementScope.CLASS, AnnouncementScope.SECTION):
        sections = Section.query.filter_by(session_id=session_id, is_active=True)
        if scope == AnnouncementScope.CLASS and announcement.school_class_id:
            sections = sections.filter_by(school_class_id=announcement.school_class_id)
        if announcement.section_id:
            sections = sections.filter_by(id=announcement.section_id)
        section_ids = [s.id for s in sections.all()]
        if section_ids:
            enrollments = Enrollment.query.filter(
                Enrollment.section_id.in_(section_ids),
                Enrollment.session_id == session_id,
                Enrollment.status == EnrollmentStatus.ACTIVE,
            ).all()
            student_ids = [e.student_id for e in enrollments]
            for student in Student.query.filter(Student.id.in_(student_ids)).all():
                if student.user_id:
                    ids.add(student.user_id)
            links = GuardianStudentLink.query.filter(
                GuardianStudentLink.student_id.in_(student_ids),
                GuardianStudentLink.receive_notifications.is_(True),
            ).all()
            for link in links:
                if link.guardian and link.guardian.user_id:
                    ids.add(link.guardian.user_id)
    return sorted(ids)


def publish_announcement(announcement: Announcement, actor_id: int | None = None) -> int:
    announcement.status = AnnouncementStatus.PUBLISHED
    if announcement.publish_at is None:
        announcement.publish_at = utcnow()
    recipients = notification_recipients(announcement)
    for user_id in recipients:
        notify_user(
            user_id=user_id,
            kind=NotificationKind.ANNOUNCEMENT,
            title=announcement.title,
            body=announcement.body[:200],
            link="/announcements",
            entity_type="Announcement",
            entity_id=announcement.id,
            school_id=announcement.school_id,
        )
    record("announcement.published", "Announcement", announcement.id,
           summary=f"{len(recipients)} recipients", actor_id=actor_id)
    db.session.commit()
    return len(recipients)


def visible_announcements(user: User, session_id: int):
    """Announcements relevant to this user, respecting scope and class."""
    query = Announcement.query.filter_by(session_id=session_id).filter(
        Announcement.status.in_([AnnouncementStatus.PUBLISHED, AnnouncementStatus.SCHEDULED])
    )
    now = utcnow()
    query = query.filter(
        or_(Announcement.publish_at.is_(None), Announcement.publish_at <= now)
    ).filter(or_(Announcement.expires_at.is_(None), Announcement.expires_at >= now))

    if user.role in (Role.SUPERUSER, Role.PRINCIPAL, Role.ADMIN):
        return query.order_by(Announcement.is_pinned.desc(), Announcement.publish_at.desc())

    scopes = {AnnouncementScope.ALL}
    section_ids: set[int] = set()

    if user.role == Role.TEACHER:
        scopes |= {AnnouncementScope.STAFF, AnnouncementScope.TEACHERS}
        from ..security.scoping import teacher_section_ids

        section_ids = teacher_section_ids(user)
    elif user.role in (Role.ACCOUNTS, Role.ADMISSIONS):
        scopes |= {AnnouncementScope.STAFF}
    elif user.role == Role.PARENT:
        scopes.add(AnnouncementScope.PARENTS)
        for link in getattr(user.guardian, "links", []) if user.guardian else []:
            enrollment = link.student.current_enrollment if link.student else None
            if enrollment:
                section_ids.add(enrollment.section_id)
    elif user.role == Role.STUDENT:
        scopes.add(AnnouncementScope.STUDENTS)
        enrollment = user.student.current_enrollment if getattr(user, "student", None) else None
        if enrollment:
            section_ids.add(enrollment.section_id)

    conditions = [Announcement.audience_scope.in_(list(scopes))]
    if section_ids:
        conditions.append(
            and_(
                Announcement.audience_scope.in_(
                    [AnnouncementScope.CLASS, AnnouncementScope.SECTION]
                ),
                Announcement.section_id.in_(list(section_ids)),
            )
        )
    query = query.filter(or_(*conditions))
    return query.order_by(Announcement.is_pinned.desc(), Announcement.publish_at.desc())


def unread_count(user_id: int) -> int:
    return Notification.query.filter_by(user_id=user_id, read_at=None).count()
