"""Application configuration.

Every environment-specific value is read from the environment so that no secret
is committed to source control.  Production configuration deliberately fails
fast when a secret is missing instead of silently falling back to a dev default.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
load_dotenv(BASE_DIR / ".env")

DEV_SECRET = "dev-only-insecure-secret-change-me"


class BaseConfig:
    APP_NAME = "School OS"
    SECRET_KEY = os.environ.get("SECRET_KEY", DEV_SECRET)

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{(INSTANCE_DIR / 'school.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Uploads live outside the web root and are served through authorised views.
    UPLOAD_FOLDER = str(INSTANCE_DIR / "uploads")
    BACKUP_FOLDER = str(INSTANCE_DIR / "backups")
    LOG_FOLDER = str(INSTANCE_DIR / "logs")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
    ALLOWED_UPLOAD_EXTENSIONS = {
        "png", "jpg", "jpeg", "webp", "pdf", "doc", "docx", "xls", "xlsx", "txt", "csv",
    }
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

    # Session hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8

    WTF_CSRF_TIME_LIMIT = 60 * 60 * 2
    WTF_CSRF_SSL_STRICT = True

    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True

    SCHOOL_TIMEZONE = "Asia/Kolkata"
    SCHOOL_CURRENCY = "INR"
    CURRENCY_SYMBOL = "₹"

    # Demo data is only ever written to a database flagged as demo.
    DEMO_MODE = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    ENV_NAME = "development"


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    ENV_NAME = "testing"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SERVER_NAME = "localhost.localdomain"


class ProductionConfig(BaseConfig):
    DEBUG = False
    ENV_NAME = "production"
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"

    def __init__(self) -> None:
        if self.SECRET_KEY in (DEV_SECRET, "", None):
            raise RuntimeError(
                "SECRET_KEY must be set to a strong random value in production."
            )
        if self.SQLALCHEMY_DATABASE_URI.startswith("sqlite:///") and "instance" not in (
            self.SQLALCHEMY_DATABASE_URI
        ):
            raise RuntimeError("Production SQLite database must live inside instance/.")


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None):
    name = name or os.environ.get("FLASK_ENV", "development")
    return CONFIG_MAP.get(name, DevelopmentConfig)
