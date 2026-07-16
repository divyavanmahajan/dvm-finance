"""Category Trends view: hierarchical category × period table with click-through.

``GET /trends`` renders the full tab; ``GET /trends/table`` serves the htmx
partial so the window/granularity/account controls swap the table while
pushing the state into the URL (same style as the Transactions view).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..core.models import CategorizationRule, Transaction
from ..core.trends import TrendsParams, aggregate, transactions_link
from ..core.utils import CATEGORY_SEPARATOR
from ..db import get_db
from ..logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


def _templates():
    from ..app import templates

    return templates


def _known_accounts(db: Session) -> list[str]:
    rows = db.query(Transaction.accountNumber).distinct().all()
    return sorted({r[0] for r in rows if r[0]})


def _known_categories(db: Session) -> list[str]:
    """Mirrors `api/transactions.py:_known_categories` — duplicated rather
    than imported, matching this module's existing precedent of its own
    `_known_accounts` rather than sharing one across route modules."""
    cats: set[str] = set()
    for col in (Transaction.category, Transaction.manual_category):
        for (value,) in db.query(col).distinct():
            if value:
                cats.add(value)
    for (value,) in db.query(CategorizationRule.category).distinct():
        if value:
            cats.add(value.lower())
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


def _context(request: Request, db: Session) -> dict:
    params = TrendsParams.from_params(request.query_params)
    table = aggregate(db, params)
    window_from, window_to = params.effective_window()
    return {
        "active_path": "/trends",
        "params": params,
        "table": table,
        "window_from": window_from,
        "window_to": window_to,
        "accounts": _known_accounts(db),
        "categories": _known_categories(db),
        "tags": _known_tags(db),
        "presets": ["this-month", "last-month", "this-year", "last-year"],
        "link": lambda categories, date_from, date_to, accounts: transactions_link(
            categories, date_from, date_to, accounts, params=params
        ),
    }


@router.get("/trends", response_class=HTMLResponse)
def trends_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return _templates().TemplateResponse(request, "trends.html", _context(request, db))


@router.get("/trends/table", response_class=HTMLResponse)
def trends_table(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return _templates().TemplateResponse(
        request, "_trends_table.html", _context(request, db)
    )
