"""Snapshots page: export/download versioned snapshots, incoming-wins import.

Claims ``GET /snapshots`` from the placeholder. Export writes a gzipped JSON
snapshot to ``<data_dir>/snapshots/`` and returns it as a browser download; the
page lists past exports and shows stored import reports. Import validates the
file, backs up the DB, then merges in one transaction (see core.snapshots).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..core.models import SnapshotImport
from ..core.snapshots import (
    SnapshotError,
    export_snapshot,
    import_snapshot,
    list_exports,
    read_snapshot,
)
from ..db import get_db
from ..logging_config import get_logger
from ..settings import Settings

router = APIRouter()
logger = get_logger(__name__)


def _templates(request: Request):
    from ..app import templates

    return templates


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _render(
    request: Request,
    db: Session,
    *,
    error: str | None = None,
    imported_id: int | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    settings = _settings(request)
    imports = (
        db.query(SnapshotImport)
        .order_by(SnapshotImport.created_at.desc(), SnapshotImport.id.desc())
        .limit(20)
        .all()
    )
    ctx = {
        "request": request,
        "active_path": "/snapshots",
        "title": "Snapshots",
        "exports": list_exports(settings.data_dir),
        "imports": imports,
        "imported_id": imported_id,
        "error": error,
    }
    return _templates(request).TemplateResponse(
        request, "snapshots.html", ctx, status_code=status_code
    )


@router.get("/snapshots", response_class=HTMLResponse, include_in_schema=False)
def snapshots_page(
    request: Request, imported: int | None = None, db: Session = Depends(get_db)
) -> HTMLResponse:
    return _render(request, db, imported_id=imported)


@router.post("/snapshots/export", include_in_schema=False)
def snapshots_export(request: Request, db: Session = Depends(get_db)) -> FileResponse:
    settings = _settings(request)
    path = export_snapshot(db, settings.data_dir)
    return FileResponse(path, filename=path.name, media_type="application/gzip")


@router.get("/snapshots/files/{name}", include_in_schema=False)
def snapshots_download(request: Request, name: str):
    settings = _settings(request)
    # Only names of actual exports in the snapshots dir are served (no traversal).
    if name not in {e["name"] for e in list_exports(settings.data_dir)}:
        return HTMLResponse("Snapshot not found", status_code=404)
    path = settings.snapshots_dir / name
    return FileResponse(path, filename=name, media_type="application/gzip")


@router.post("/snapshots/import", include_in_schema=False)
async def snapshots_import(
    request: Request, file: UploadFile, db: Session = Depends(get_db)
):
    settings = _settings(request)
    blob = await file.read()
    try:
        payload = read_snapshot(blob)
    except SnapshotError as exc:
        logger.info("snapshot_rejected", reason=str(exc), filename=file.filename)
        return _render(request, db, error=str(exc), status_code=400)

    # import_snapshot backs up the DB file first and merges in ONE transaction;
    # it does NOT reapply rules — the snapshot's categorization is authoritative.
    result = import_snapshot(db, payload, settings.db_path)
    return RedirectResponse(url=f"/snapshots?imported={result.id}", status_code=303)
