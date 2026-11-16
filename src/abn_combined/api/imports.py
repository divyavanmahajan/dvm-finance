"""Import page: the bank download sources and the statement upload form.

The page combines the old Download and Upload pages. ``GET /download`` and
``GET /upload`` redirect here, so old bookmarks still work. The start-job,
status and upload endpoints stay in ``api/downloads.py`` and ``api/upload.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from .downloads import download_context
from .sample_data import sample_data_context
from .upload import upload_context

router = APIRouter()


def redirect_keeping_query(request: Request, path: str) -> RedirectResponse:
    """A 307 redirect to *path* that keeps the query string of *request*."""
    query = request.url.query
    return RedirectResponse(f"{path}?{query}" if query else path, status_code=307)


@router.get("/import", response_class=HTMLResponse, include_in_schema=False)
def import_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    from ..app import templates

    ctx = {"active_path": "/import", "title": "Import"}
    ctx.update(download_context(db))
    ctx.update(upload_context())
    ctx.update(sample_data_context(db))
    return templates.TemplateResponse(request, "import.html", ctx)


@router.get("/download", include_in_schema=False)
def download_redirect(request: Request) -> RedirectResponse:
    return redirect_keeping_query(request, "/import")


@router.get("/upload", include_in_schema=False)
def upload_redirect(request: Request) -> RedirectResponse:
    return redirect_keeping_query(request, "/import")
