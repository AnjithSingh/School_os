# Progress

Updated: 2 November 2026

## Status summary

| Area | State | Notes |
|------|-------|-------|
| Foundation | Done | App factory, config, extensions, CLI, error pages, security headers |
| Identity & auth | Done | Staff/parent/student login, lockout, password reset tokens, forced password change |
| Academic structure | Done | Sessions, classes 6-10, sections per session, subjects, allocations |
| Students & guardians | Done | Admissions, enrollment, transfers, guardian links with per-link permissions |
| Staff | Done | Profiles, staff types, leave applications and review |
| Attendance | Done | Section registers, corrections with audit, student/section summaries |
| Timetable | Done | Period grid per section, teacher view, admin editing |
| Examinations | Done | Configurable exam types, subject sheets, marks entry/approval, grading |
| Results & report cards | Done | Computed results, immutable snapshots, revisions, PDF, publish |
| Homework | Done | Teacher authoring, submissions, parent/student visibility |
| Fees | Done | Structures, generation, concessions, payments, reversals, receipts |
| Announcements | Done | Audience targeting, publish window, attachments |
| Parent portal | Done | Per-child dashboard, attendance, results, cards, fees, leave, notices |
| Student portal | Done | Dashboard, timetable, attendance, homework, materials, results, cards |
| Admin reports | Done | Attendance, fees and results summaries with local Chart.js |
| Audit trail | Done | Sensitive writes recorded with actor and summary |
| Migrations | Done | Initial Alembic revision `6dddd46f26c9` at head |
| Tests | Done | 81 passing tests across permissions, auth, attendance, exams, fees, PDFs |
| Documentation | Done | README, this file, known limitations |

## Verification snapshot

- 147 URL rules registered.
- Full GET smoke sweep: admin, principal, accounts and teacher routes, zero failures.
- Parent and student portal smoke sweeps: zero failures for both demo children.
- `flask db upgrade` on the development database is a clean no-op.
- pytest: 81 passed.

## Module completion definition

A module is treated as complete only when models, validation, persistence,
server-side permissions, error states, responsive UI and tests all work. The
table above reflects that bar; deferred items are listed in
`KNOWN_LIMITATIONS.md` rather than counted as done.

## Suggested next milestones

1. Term-weighted result aggregation (FA + SA) and configurable report templates.
2. Parent-teacher messaging with moderation and read receipts.
3. Bulk student import/export and document checklists for admissions.
4. Optional student PIN login and device remember-me policy.
5. Multi-school tenancy: school switcher, scoped queries and per-school settings.
6. Automated database backups on a schedule with restore verification.
