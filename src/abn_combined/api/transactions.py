"""Transactions view: filtered/paginated table, inline manual edits, row detail.

The tab lives at ``/`` (the main screen). ``/transactions`` is kept as an alias so
deep-links built by other steps (e.g. ``/transactions?rule_id=N`` or
``?source_file=...``) keep working. The htmx table partial is served from
``/transactions/table`` for both routes.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..core.filters import (
    TransactionFilter,
    effective_category,
    effective_tags,
    is_manual,
    paginate,
)
from ..core.models import CategorizationRule, Transaction
from ..core.utils import CATEGORY_SEPARATOR, normalize_category
from ..db import get_db
from ..logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


def _templates(request: Request):
    from ..app import templates

    return templates


# ---------------------------------------------------------------------------
# Facet options (accounts / categories / tags) for the filter bar
# ---------------------------------------------------------------------------


def _known_accounts(db: Session) -> list[str]:
    rows = db.query(Transaction.accountNumber).distinct().all()
    return sorted({r[0] for r in rows if r[0]})


def _known_categories(db: Session) -> list[str]:
    cats: set[str] = set()
    for col in (Transaction.category, Transaction.manual_category):
        for (value,) in db.query(col).distinct():
            if value:
                cats.add(value)
    # Rule categories too, so a fresh DB still offers targets.
    for (value,) in db.query(CategorizationRule.category).distinct():
        if value:
            cats.add(value.lower())
    # Ancestor prefixes so whole subtrees can be included/excluded
    # (selecting "fixed-insurance" also covers "fixed-insurance-life").
    for cat in list(cats):
        parts = cat.split(CATEGORY_SEPARATOR)
        for i in range(1, len(parts)):
            cats.add(CATEGORY_SEPARATOR.join(parts[:i]))
    return sorted(cats)


def _known_tags(db: Session) -> list[str]:
    tags: set[str] = set()
    for col in (Transaction.tags, Transaction.manual_tags):
        for (value,) in db.query(col).distinct():
            if value:
                for part in value.split(","):
                    part = part.strip()
                    if part:
                        tags.add(part)
    return sorted(tags)


def _row_view(txn: Transaction) -> dict:
    """A display-ready view-model for one transaction row."""
    return {
        "txn": txn,
        "effective_category": effective_category(txn),
        "effective_tags": effective_tags(txn),
        "is_manual": is_manual(txn),
    }


def _structured_fields(txn: Transaction) -> dict:
    if not txn.description_structured:
        return {}
    try:
        data = json.loads(txn.description_structured)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _rule_for_source(db: Session, source: str | None) -> CategorizationRule | None:
    if not source or source == "manual":
        return None
    try:
        rid = int(source)
    except ValueError:
        return None
    return db.get(CategorizationRule, rid)


def _table_context(request: Request, db: Session, f: TransactionFilter) -> dict:
    page = paginate(db, f)
    return {
        "request": request,
        "filter": f,
        "qs": f.to_query_string(),
        "page": page,
        "rows": [_row_view(t) for t in page.items],
        "chips": f.active_chips(),
    }


def _get_txn_or_404(db: Session, transaction_id: str) -> Transaction:
    txn = db.get(Transaction, transaction_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


# ---------------------------------------------------------------------------
# Page + partial routes
# ---------------------------------------------------------------------------


def _render_page(request: Request, db: Session, active_path: str) -> HTMLResponse:
    f = TransactionFilter.from_params(request.query_params)
    ctx = _table_context(request, db, f)
    ctx.update(
        {
            "active_path": active_path,
            "title": "Transactions",
            "accounts": _known_accounts(db),
            "categories": _known_categories(db),
            "tags": _known_tags(db),
            "presets": ["this-month", "last-month", "this-year", "last-year"],
        }
    )
    return _templates(request).TemplateResponse(request, "transactions.html", ctx)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def transactions_index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return _render_page(request, db, active_path="/")


@router.get("/transactions", response_class=HTMLResponse, include_in_schema=False)
def transactions_alias(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    # Secondary route so /transactions?rule_id=N deep-links resolve; still marks
    # the Transactions ("/") nav tab active.
    return _render_page(request, db, active_path="/")


@router.get("/transactions/table", response_class=HTMLResponse, include_in_schema=False)
def transactions_table(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    f = TransactionFilter.from_params(request.query_params)
    ctx = _table_context(request, db, f)
    return _templates(request).TemplateResponse(request, "_transactions_table.html", ctx)


@router.get("/transactions/{transaction_id}/detail", response_class=HTMLResponse,
            include_in_schema=False)
def transaction_detail(request: Request, transaction_id: str,
                       db: Session = Depends(get_db)) -> HTMLResponse:
    txn = _get_txn_or_404(db, transaction_id)
    rule = _rule_for_source(db, txn.categorization_source)
    ctx = {
        "request": request,
        "row": _row_view(txn),
        "structured": _structured_fields(txn),
        "rule": rule,
    }
    return _templates(request).TemplateResponse(request, "_transaction_detail.html", ctx)


# ---------------------------------------------------------------------------
# Inline manual edit + clear
# ---------------------------------------------------------------------------


def _row_response(request: Request, db: Session, txn: Transaction) -> HTMLResponse:
    ctx = {"request": request, "row": _row_view(txn),
           "filter": TransactionFilter.from_params(request.query_params)}
    return _templates(request).TemplateResponse(request, "_transactions_row.html", ctx)


@router.post("/transactions/{transaction_id}/category", response_class=HTMLResponse,
             include_in_schema=False)
def set_manual_category(request: Request, transaction_id: str,
                        manual_category: str = Form(""),
                        db: Session = Depends(get_db)) -> HTMLResponse:
    """Set the manual category (manual precedence, source=manual)."""
    txn = _get_txn_or_404(db, transaction_id)
    txn.manual_category = normalize_category(manual_category)
    txn.categorization_source = "manual"
    db.commit()
    logger.info("manual_category_set", txn=transaction_id, category=txn.manual_category)
    return _row_response(request, db, txn)


@router.post("/transactions/{transaction_id}/tags", response_class=HTMLResponse,
             include_in_schema=False)
def set_manual_tags(request: Request, transaction_id: str,
                    manual_tags: str = Form(""),
                    db: Session = Depends(get_db)) -> HTMLResponse:
    """Set manual tags (comma-separated, manual precedence, source=manual)."""
    txn = _get_txn_or_404(db, transaction_id)
    cleaned = ", ".join(p.strip() for p in manual_tags.split(",") if p.strip())
    txn.manual_tags = cleaned or None
    txn.categorization_source = "manual"
    db.commit()
    logger.info("manual_tags_set", txn=transaction_id, tags=txn.manual_tags)
    return _row_response(request, db, txn)


@router.delete("/transactions/{transaction_id}/category", response_class=HTMLResponse,
               include_in_schema=False)
def clear_manual_category(request: Request, transaction_id: str,
                          db: Session = Depends(get_db)) -> HTMLResponse:
    """Clear the manual category, restoring the rule-assigned value.

    Mirrors abn-analyst ``transactions.py:448``: reset ``categorization_source``
    when it was ``"manual"`` and no manual tags remain.
    """
    txn = _get_txn_or_404(db, transaction_id)
    txn.manual_category = None
    if txn.categorization_source == "manual" and not txn.manual_tags:
        txn.categorization_source = None
    db.commit()
    logger.info("manual_category_cleared", txn=transaction_id)
    return _row_response(request, db, txn)


@router.delete("/transactions/{transaction_id}/tags", response_class=HTMLResponse,
               include_in_schema=False)
def clear_manual_tags(request: Request, transaction_id: str,
                      db: Session = Depends(get_db)) -> HTMLResponse:
    """Clear manual tags, restoring the rule-assigned value."""
    txn = _get_txn_or_404(db, transaction_id)
    txn.manual_tags = None
    if txn.categorization_source == "manual" and not txn.manual_category:
        txn.categorization_source = None
    db.commit()
    logger.info("manual_tags_cleared", txn=transaction_id)
    return _row_response(request, db, txn)
