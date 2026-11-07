# School OS

A single-school management platform built with Flask and SQLite. It covers
admissions, staff, attendance, timetable, examinations, report cards, homework,
fees, announcements and separate parent and student portals.

The schema is single-tenant in v1 but every tenant-owned table carries a
`school_id`, so a future multi-school deployment can add school scoping without
rewriting the data model.

## Stack

- Python 3.10+, Flask 3 blueprints, Flask-SQLAlchemy, Flask-Login, Flask-WTF
- Flask-Migrate (Alembic) for schema history
- SQLite for storage, Jinja2 templates, hand-written CSS design system
- Chart.js vendored locally (no CDN requests)
- ReportLab for report cards and fee receipts
- pytest + pytest-cov

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
# Edit .env and set a strong SECRET_KEY.

$env:FLASK_APP = "run.py"
flask db upgrade
flask seed-demo          # optional demo school
flask run
```

Open <http://127.0.0.1:5000>. If the database is empty the app redirects to
`/setup`, where the first school and owner account are created.

### Demo credentials (only after `flask seed-demo`)

| Portal  | Username   | Password         |
|---------|------------|------------------|
| Staff   | `admin`    | `Admin@12345`    |
| Staff   | `principal`| `Principal@12345`|
| Staff   | `accounts` | `Accounts@12345` |
| Staff   | `teacher1` | `Teacher@12345`  |
| Parent  | `parent`   | `Parent@12345`   |
| Student | `student`  | `Student@12345`  |

Sign-in screens are intentionally separate: `/login`, `/parent/login` and
`/student/login`. A parent or student account cannot be used on the staff login
and vice versa.

## CLI

```powershell
$env:FLASK_APP = "run.py"
flask init-db            # create tables on an empty database
flask reset-db --yes     # drop and recreate (development only)
flask create-user --username ... --full-name ... --role ADMIN
flask set-password --username ...
flask backup --note "before term 2"
flask seed-demo [--force]
```

Run migrations with `flask db upgrade`; create new ones with
`flask db migrate -m "message"` after changing models.

## Layout

```
app/
  models/        SQLAlchemy models and enums
  services/      business rules, validation, audit and PDF orchestration
  routes/        staff, parent, student, file-delivery and JSON endpoints
  forms/         WTForms definitions and validators
  security/      permissions, route guards and row-level scoping
  templates/     layouts, portals, admin screens, shared partials
  static/        design-system CSS, core JS, vendored Chart.js
migrations/      Alembic history
tests/           service and route tests built on a complete demo school
docs/            progress and known-limitations notes
```

## Access model

- Authentication and authorization are enforced on the server for every
  sensitive route; templates only hide actions the user cannot perform.
- Staff permissions come from `app/security/permissions.py`. Teachers are
  additionally scoped to the sections they teach via `teacher_section_ids()`.
- Parent permissions live on each `GuardianStudentLink`, not on the guardian.
  The child is always part of the URL (`/parent/children/<id>/...`) so an
  accidental session switch cannot expose another family's data.
- Student routes resolve the student from the authenticated account; a student
  id is never accepted from the URL.
- Generated PDFs and uploads live outside `static/` and are delivered only
  through `routes/files.py`, which re-checks the relationship to each file.

## Money, results and history

- Money is stored as integer paise (`*_paise`), never floats.
- Report cards store an immutable JSON snapshot plus a generated PDF and a
  revision number. Publishing freezes the current revision; later corrections
  create a new revision rather than rewriting history.
- Exam types and grade bands are database configuration, not constants.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing
```

The suite builds a complete school through the service layer (not raw inserts)
and covers permissions, portal separation, attendance, examinations, fees,
report-card PDFs and download authorization. The current suite has 81 passing
tests.

Tests use an in-memory SQLite database. The fixture keeps one application
context alive for service calls and explicitly clears Flask-Login's `g` cache
before each request so separate test clients keep separate sessions.

## Production notes

- Set `SECRET_KEY` to a strong random value and `FLASK_ENV=production`.
- Serve through Waitress or Gunicorn (`wsgi:app`), not the Flask dev server.
- Put the app behind HTTPS; production config enables secure cookies and HSTS
  when the request is secure.
- Keep `instance/` (database, uploads, backups, logs) out of version control
  and back it up regularly.
- The CSP allows only same-origin scripts. Inline `onclick` handlers are blocked;
  use `data-*` attributes handled by `static/js/core.js`.

See `docs/PROGRESS.md` for module status and `docs/KNOWN_LIMITATIONS.md` for
what is intentionally deferred.
