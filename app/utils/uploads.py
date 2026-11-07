"""Secure file upload handling.

Files are stored outside the web root with random names, validated by extension
and (for images) by magic bytes, and served only through an authorised view.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import StoredFile

_MAGIC = {
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "webp": [b"RIFF"],
    "pdf": [b"%PDF-"],
}


class UploadError(Exception):
    pass


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _sniff_ok(stream, ext: str) -> bool:
    signatures = _MAGIC.get(ext)
    if not signatures:
        return True  # non-binary formats are constrained by the allow-list
    head = stream.read(8)
    stream.seek(0)
    return any(head.startswith(sig) for sig in signatures)


def save_upload(file_storage, category: str = "general", user_id: int | None = None) -> StoredFile:
    if file_storage is None or not getattr(file_storage, "filename", ""):
        raise UploadError("Please choose a file.")

    original = secure_filename(file_storage.filename) or "upload"
    ext = _extension(original)
    allowed = current_app.config["ALLOWED_UPLOAD_EXTENSIONS"]
    if ext not in allowed:
        raise UploadError(
            f"'{ext or 'unknown'}' files are not allowed. Allowed: {', '.join(sorted(allowed))}."
        )
    if not _sniff_ok(file_storage.stream, ext):
        raise UploadError("That file does not look like a valid " + ext.upper() + " file.")

    folder = Path(current_app.config["UPLOAD_FOLDER"]) / category
    folder.mkdir(parents=True, exist_ok=True)

    identifier = uuid.uuid4().hex
    stored_name = f"{identifier}.{ext}"
    destination = folder / stored_name

    file_storage.save(destination)
    size = destination.stat().st_size
    max_bytes = current_app.config["MAX_CONTENT_LENGTH"]
    if size > max_bytes:
        destination.unlink(missing_ok=True)
        raise UploadError("File is larger than the 10 MB limit.")
    if size == 0:
        destination.unlink(missing_ok=True)
        raise UploadError("The file is empty.")

    digest = hashlib.sha256(destination.read_bytes()).hexdigest()

    record = StoredFile(
        school_id=_school_id(),
        uuid=identifier,
        original_name=original,
        stored_path=str(destination),
        mime=file_storage.mimetype or "application/octet-stream",
        size_bytes=size,
        sha256=digest,
        category=category,
        uploaded_by_id=user_id,
    )
    db.session.add(record)
    db.session.flush()
    return record


def delete_upload(record: StoredFile | None) -> None:
    if record is None:
        return
    try:
        Path(record.stored_path).unlink(missing_ok=True)
    except OSError:
        pass
    record.deleted_at = record.updated_at


def _school_id() -> int:
    from ..services.settings import get_school

    school = get_school()
    if school is None:
        raise UploadError("School profile has not been configured yet.")
    return school.id
