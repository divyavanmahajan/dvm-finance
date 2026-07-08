"""Manual upload endpoint and Upload page."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from ..core.importer import VALID_FORMATS, ImportError_, ImportSummary, import_file
from ..db import get_db
from ..logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


class UploadParams(BaseModel):
    """Boundary validation for the upload form's non-file fields."""

    format: Literal["auto", "paypal", "wise", "seb", "csv"] = "auto"


def _templates(request: Request):
    from ..app import templates

    return templates


@router.get("/upload", response_class=HTMLResponse, include_in_schema=False)
def upload_page(request: Request) -> HTMLResponse:
    return _templates(request).TemplateResponse(
        request,
        "upload.html",
        {"active_path": "/upload", "title": "Upload", "formats": VALID_FORMATS},
    )


@router.post("/api/upload")
async def api_upload(
    request: Request,
    file: UploadFile = File(...),
    format: str = Form("auto"),
    db: Session = Depends(get_db),
):
    """Accept a statement file, import it, and return an inline summary partial."""
    try:
        params = UploadParams(format=format)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid format: {format}") from exc

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    settings = request.app.state.settings
    try:
        summary: ImportSummary = import_file(
            db,
            content,
            file.filename or "upload.dat",
            statements_dir=settings.statements_dir,
            fmt=params.format,
        )
    except ImportError_ as exc:
        logger.info("upload_rejected", filename=file.filename, error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info(
        "upload_imported",
        filename=summary.source_file,
        new=summary.new,
        duplicates=summary.duplicates,
    )

    # htmx requests get the inline partial; plain API clients get JSON.
    if request.headers.get("HX-Request"):
        return _templates(request).TemplateResponse(
            request, "_upload_summary.html", {"summary": summary}
        )
    return summary.as_dict()
