"""Tags page: list all tags with usage counts, rename, delete.

Usage counts merge rule-assigned (``tags``) and manual (``manual_tags``) columns,
deduplicated per transaction (legacy abn-analyst semantics). Each tag links to
``/transactions?tag=<name>`` — the exact param name used by
:class:`~abn_combined.core.filters.TransactionFilter`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..constants import is_transfer_category
from ..core.models import Transaction
from ..core.renames import delete_tag, rename_tag
from ..db import get_db
from ..logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


def _templates(request: Request):
    from ..app import templates

    return templates


def collect_tags(db: Session, exclude_transfers: bool = True) -> list[dict]:
    """All tags with usage counts and credit/debit totals, sorted by count desc.

    Args:
        db: Database session
        exclude_transfers: If True (default), exclude transfer transactions
    """
    query = db.query(Transaction).filter(
        (Transaction.tags.isnot(None)) | (Transaction.manual_tags.isnot(None))
    )
    # Exclude transfers by default
    if exclude_transfers:
        eff_cat = Transaction.manual_category
        eff_cat_fallback = Transaction.category
        # Use the effective category expression (manual takes precedence)
        from sqlalchemy import func
        eff = func.coalesce(func.nullif(eff_cat, ""), eff_cat_fallback)
        query = query.filter(
            or_(eff.is_(None), eff == "", ~eff.ilike('%transfer%'))
        )
    txns = query.all()
    data: dict[str, dict] = {}
    for txn in txns:
        names: set[str] = set()
        for value in (txn.tags, txn.manual_tags):
            if value:
                names.update(p.strip() for p in value.split(",") if p.strip())
        amount = float(txn.amount) if txn.amount else 0.0
        for name in names:
            entry = data.setdefault(
                name,
                {"name": name, "count": 0, "credit_amount": 0.0, "debit_amount": 0.0},
            )
            entry["count"] += 1
            if amount > 0:
                entry["credit_amount"] += amount
            elif amount < 0:
                entry["debit_amount"] += abs(amount)
    return sorted(data.values(), key=lambda t: (-t["count"], t["name"]))


def _render(request: Request, db: Session, error: str | None = None,
            message: str | None = None) -> HTMLResponse:
    ctx = {
        "request": request,
        "active_path": "/tags",
        "title": "Tags",
        "tags": collect_tags(db),
        "error": error,
        "message": message,
    }
    return _templates(request).TemplateResponse(request, "tags.html", ctx)


@router.get("/tags", response_class=HTMLResponse, include_in_schema=False)
def tags_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return _render(request, db)


@router.post("/tags/rename", include_in_schema=False)
def tags_rename(request: Request, old: str = Form(...), new: str = Form(...),
                db: Session = Depends(get_db)):
    stats = rename_tag(db, old, new)
    if "error" in stats:
        return _render(request, db, error=stats["error"])
    total = sum(v for v in stats.values() if isinstance(v, int))
    logger.info("tag_rename_requested", old=old, new=new, total=total)
    return RedirectResponse("/tags", status_code=303)


@router.post("/tags/delete", include_in_schema=False)
def tags_delete(request: Request, name: str = Form(...),
                db: Session = Depends(get_db)):
    stats = delete_tag(db, name)
    logger.info("tag_delete_requested", name=name, **stats)
    return RedirectResponse("/tags", status_code=303)
