"""Stored-file generation helpers (PDFs created by the application)."""
from __future__ import annotations

import hashlib
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from flask import current_app

from ..extensions import db
from ..models import StoredFile
from .settings import get_school


def store_generated_pdf(source_path: str | Path, filename: str, category: str = "generated",
                        user_id: int | None = None) -> StoredFile:
    source = Path(source_path)
    school = get_school()
    folder = Path(current_app.config["UPLOAD_FOLDER"]) / category
    folder.mkdir(parents=True, exist_ok=True)

    identifier = uuid.uuid4().hex
    destination = folder / f"{identifier}.pdf"
    shutil.move(str(source), destination)

    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    record = StoredFile(
        school_id=school.id,
        uuid=identifier,
        original_name=filename,
        stored_path=str(destination),
        mime="application/pdf",
        size_bytes=destination.stat().st_size,
        sha256=digest,
        category=category,
        uploaded_by_id=user_id,
    )
    db.session.add(record)
    db.session.flush()
    return record


def build_filename(prefix: str, suffix: str = "") -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{stamp}{suffix}.pdf"
