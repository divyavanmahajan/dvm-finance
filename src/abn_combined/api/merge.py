"""The page of the merge of the duplicate rows.

The bank writes one SEPA payment in two description forms. A database from
before the reference check can therefore hold one payment twice. This module
holds the routes that preview the merge, run it, and undo it. The core module
``core/merge.py`` holds the rules; this module only shows the result.

The routes are:

- ``GET /merge`` previews each group, and changes no row.
- ``POST /merge/run`` merges each group that holds no conflict.
- ``POST /merge/{survivor_id}/undo`` undoes one merge.

The merge flags each row that it folds away. It deletes no row, so the user can
undo it. The purge keeps each merged row.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..core.merge import merge_duplicates, preview_merge, undo_merge
from ..core.models import MergeReport, Transaction
from ..db import get_db
from ..logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)

#: The form must hold one of these values before the merge changes a row.
CONFIRM_VALUES = {"yes", "on", "true", "1"}


def _templates(request: Request):
    # The import is local, because ``app`` imports this module.
    from ..app import templates

    return templates


def _rows_by_id(db: Session, ids: list[str]) -> dict[str, Transaction]:
    """Return each named row, so that the page can show its date and amount."""
    if not ids:
        return {}
    rows = db.query(Transaction).filter(Transaction.id.in_(ids)).all()
    return {row.id: row for row in rows}


def _render(
    request: Request,
    db: Session,
    *,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Show each group, each refused group, and the last report."""
    preview = preview_merge(db)

    wanted: list[str] = []
    for group in preview.groups:
        wanted.append(group.survivor_id)
        wanted.extend(group.merged_ids)
    for refused in preview.refused:
        wanted.extend(refused.row_ids)

    last_report = (
        db.query(MergeReport).order_by(MergeReport.created_at.desc()).first()
    )

    ctx = {
        "request": request,
        "active_path": "/merge",
        "title": "The duplicate transactions",
        "groups": preview.groups,
        "refused": preview.refused,
        "row_count": preview.row_count,
        "rows": _rows_by_id(db, wanted),
        "last_report": last_report,
        "error": error,
        "merged": request.query_params.get("merged"),
        "restored": request.query_params.get("restored"),
    }
    return _templates(request).TemplateResponse(
        request, "merge.html", ctx, status_code=status_code
    )


@router.get("/merge", response_class=HTMLResponse, include_in_schema=False)
def merge_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Preview each group of duplicate rows. The route changes no row."""
    return _render(request, db)


@router.post("/merge/run", include_in_schema=False)
def merge_run(
    request: Request,
    confirm: str = Form(""),
    db: Session = Depends(get_db),
):
    """Merge each group that holds no conflict of the manual categories.

    The route changes nothing until the form holds the confirmation, because the
    merge changes each total.
    """
    if confirm.strip().lower() not in CONFIRM_VALUES:
        logger.info("merge_refused")
        return _render(
            request,
            db,
            error="Confirm the merge first. The system changed no transaction.",
            status_code=400,
        )

    result = merge_duplicates(db)
    logger.info(
        "merge_ok", groups=len(result.groups), rows=result.row_count
    )
    return RedirectResponse(f"/merge?merged={result.row_count}", status_code=303)


@router.post("/merge/{survivor_id}/undo", include_in_schema=False)
def merge_undo(
    request: Request,
    survivor_id: str,
    db: Session = Depends(get_db),
):
    """Undo one merge. Each folded row appears again in each list and total."""
    restored = undo_merge(db, survivor_id)
    logger.info("merge_undo", survivor=survivor_id, restored=len(restored))
    return RedirectResponse(f"/merge?restored={len(restored)}", status_code=303)
