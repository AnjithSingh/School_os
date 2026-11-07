"""WSGI entry point used by production servers and the Flask CLI."""
from app import create_app

app = create_app()
