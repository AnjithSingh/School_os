"""Server-side pagination helper used by every list view."""
from __future__ import annotations

from flask import request


def page_args(default_per_page: int = 20, max_per_page: int = 100):
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = min(max(int(request.args.get("per_page", default_per_page)), 5), max_per_page)
    except (TypeError, ValueError):
        per_page = default_per_page
    return page, per_page


def paginate(query, page: int | None = None, per_page: int | None = None):
    if page is None or per_page is None:
        default_page, default_size = page_args()
        page = page or default_page
        per_page = per_page or default_size
    return query.paginate(page=page, per_page=per_page, error_out=False)
