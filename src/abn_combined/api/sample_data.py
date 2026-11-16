"""Load and remove the fictional sample dataset (see ``core.sample_data``).

Both actions are POST only, so a GET request never changes a row. An htmx
request gets the ``_sample_data.html`` fragment back. A plain form post gets a
303 redirect to the page that sent it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from ..core import sample_data
from ..db import get_db
from ..logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


def sample_data_context(db: Session) -> dict:
    """The template context that the ``_sample_data.html`` fragment reads."""
    return {"sample_loaded": sample_data.is_loaded(db), "sample_message": None}


def _respond(request: Request, db: Session, message: str, refresh: bool) -> Response:
    if not request.headers.get("HX-Request"):
        return RedirectResponse(request.headers.get("referer") or "/", status_code=303)
    from ..app import templates

    ctx = sample_data_context(db)
    ctx["sample_message"] = message
    response = templates.TemplateResponse(request, "_sample_data.html", ctx)
    if refresh:
        # The empty Transactions page reloads, so that it shows the new rows.
        response.headers["HX-Refresh"] = "true"
    return response


@router.post("/sample-data/load", include_in_schema=False)
def sample_data_load(
    request: Request, refresh: str = Form(""), db: Session = Depends(get_db)
) -> Response:
    counts = sample_data.load(db)
    logger.info("sample_data_loaded", transactions=counts.transactions, budgets=counts.budgets)
    message = f"Loaded {counts.transactions} transactions and {counts.budgets} budgets."
    return _respond(request, db, message, refresh=bool(refresh))


@router.post("/sample-data/remove", include_in_schema=False)
def sample_data_remove(request: Request, db: Session = Depends(get_db)) -> Response:
    counts = sample_data.remove(db)
    logger.info("sample_data_removed", transactions=counts.transactions, budgets=counts.budgets)
    message = f"Removed {counts.transactions} transactions and {counts.budgets} budgets."
    return _respond(request, db, message, refresh=False)
