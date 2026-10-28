"""The pages of the hand-entered transactions.

A hand-entered transaction records a payment that no statement reports, for
example a cash payment. This module holds the routes that create, edit, flag,
restore, and purge such a transaction. The core module ``core/manual_txn.py``
holds the rules; this module only reads the form and shows the result.

The routes are:

- ``GET /manual`` shows the create form.
- ``POST /manual/create`` creates one transaction.
- ``GET /manual/{txn_id}/edit`` shows the edit form.
- ``POST /manual/{txn_id}/update`` changes one transaction.
- ``POST /manual/{txn_id}/flag`` flags one transaction for removal.
- ``POST /manual/{txn_id}/restore`` removes the flag again.
- ``GET /manual/flagged`` lists each flagged transaction.
- ``POST /manual/purge`` deletes each flagged transaction.

Caution: the purge is irreversible. The purge route therefore refuses the
request until the user confirms it.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..core.manual_txn import (
    ManualTransactionError,
    create_manual_transaction,
    edit_manual_transaction,
    flag_manual_transaction,
    purge_flagged_transactions,
    restore_manual_transaction,
)
from ..core.models import CategorizationRule, Transaction
from ..db import get_db
from ..logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)

#: The form must hold one of these values before the purge deletes a row.
CONFIRM_VALUES = {"yes", "on", "true", "1"}


def _templates(request: Request):
    # The import is local, because ``app`` imports this module.
    from ..app import templates

    return templates


def _known_categories(db: Session) -> list[str]:
    """Return each category that the database knows, for the datalist."""
    cats: set[str] = set()
    columns = (
        Transaction.category,
        Transaction.manual_category,
        CategorizationRule.category,
    )
    for col in columns:
        for (value,) in db.query(col).distinct():
            if value:
                cats.add(value.lower())
    return sorted(cats)


def _parse_date(value: str) -> date | None:
    """Return the date of the form value, or None for an empty value.

    Raise :class:`ManualTransactionError` for a value that is not a date.
    """
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ManualTransactionError(
            "The date is not correct. Use the form YYYY-MM-DD."
        ) from None


def _get_manual_or_refuse(db: Session, txn_id: str) -> Transaction:
    """Return one hand-entered transaction, or raise the refusal."""
    txn = db.query(Transaction).filter(Transaction.id == txn_id).one_or_none()
    if txn is None:
        raise HTTPException(status_code=404, detail="The transaction is not found.")
    if not txn.is_manual:
        raise HTTPException(
            status_code=400,
            detail=(
                "The system refuses the operation. "
                "The transaction is imported, and only a hand-entered "
                "transaction accepts an edit, a flag, or a restore."
            ),
        )
    return txn


# ---------------------------------------------------------------------------
# 5.1 The create route and the create form
# ---------------------------------------------------------------------------


def _render_new(
    request: Request,
    db: Session,
    error: str | None = None,
    form: dict | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Show the create form, with the error and the typed values."""
    ctx = {
        "request": request,
        "active_path": "/manual",
        "title": "Add a cash transaction",
        "error": error,
        "form": form or {},
        "categories": _known_categories(db),
        "created": request.query_params.get("created"),
        "today": date.today().isoformat(),
    }
    return _templates(request).TemplateResponse(
        request, "manual_new.html", ctx, status_code=status_code
    )


@router.get("/manual", response_class=HTMLResponse, include_in_schema=False)
def manual_new_form(
    request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    """Show the form that creates one hand-entered transaction."""
    return _render_new(request, db)


@router.post("/manual/create", include_in_schema=False)
def manual_create(
    request: Request,
    transactiondate: str = Form(""),
    amount: str = Form(""),
    description: str = Form(""),
    category: str = Form(""),
    tags: str = Form(""),
    db: Session = Depends(get_db),
):
    """Create one hand-entered transaction in the account CASH.

    The date, the amount, and the description are required. The system writes
    nothing when it refuses a value.
    """
    form = {
        "transactiondate": transactiondate,
        "amount": amount,
        "description": description,
        "category": category,
        "tags": tags,
    }
    try:
        txn_date = _parse_date(transactiondate)
        txn = create_manual_transaction(
            db,
            transactiondate=txn_date,
            amount=amount,
            description=description,
            category=category or None,
            tags=tags or None,
        )
    except ManualTransactionError as exc:
        db.rollback()
        logger.info("manual_create_refused", reason=str(exc))
        return _render_new(request, db, error=str(exc), form=form, status_code=400)
    logger.info("manual_create_ok", txn=txn.id)
    return RedirectResponse("/manual?created=1", status_code=303)


# ---------------------------------------------------------------------------
# 5.2 The edit route and the edit form
# ---------------------------------------------------------------------------


def _render_edit(
    request: Request,
    db: Session,
    txn: Transaction,
    error: str | None = None,
    form: dict | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Show the edit form of one hand-entered transaction."""
    values = form or {
        "transactiondate": (
            txn.transactiondate.isoformat() if txn.transactiondate else ""
        ),
        "amount": "" if txn.amount is None else str(txn.amount),
        "description": txn.description or "",
        "category": txn.manual_category or txn.category or "",
        "tags": txn.manual_tags or txn.tags or "",
    }
    ctx = {
        "request": request,
        "active_path": "/manual",
        "title": "Edit the cash transaction",
        "txn": txn,
        "error": error,
        "form": values,
        "categories": _known_categories(db),
    }
    return _templates(request).TemplateResponse(
        request, "manual_edit.html", ctx, status_code=status_code
    )


@router.get(
    "/manual/{txn_id}/edit", response_class=HTMLResponse, include_in_schema=False
)
def manual_edit_form(
    request: Request, txn_id: str, db: Session = Depends(get_db)
) -> HTMLResponse:
    """Show the edit form. The system refuses an imported transaction."""
    txn = _get_manual_or_refuse(db, txn_id)
    return _render_edit(request, db, txn)


@router.post("/manual/{txn_id}/update", include_in_schema=False)
def manual_update(
    request: Request,
    txn_id: str,
    transactiondate: str = Form(""),
    amount: str = Form(""),
    description: str = Form(""),
    category: str = Form(""),
    tags: str = Form(""),
    db: Session = Depends(get_db),
):
    """Change one hand-entered transaction. The transaction keeps its id."""
    txn = _get_manual_or_refuse(db, txn_id)
    form = {
        "transactiondate": transactiondate,
        "amount": amount,
        "description": description,
        "category": category,
        "tags": tags,
    }
    try:
        txn_date = _parse_date(transactiondate)
        edit_manual_transaction(
            db,
            txn_id,
            transactiondate=txn_date,
            amount=amount,
            description=description,
            category=category or None,
            tags=tags or None,
        )
    except ManualTransactionError as exc:
        db.rollback()
        logger.info("manual_update_refused", txn=txn_id, reason=str(exc))
        return _render_edit(
            request, db, txn, error=str(exc), form=form, status_code=400
        )
    logger.info("manual_update_ok", txn=txn_id)
    return RedirectResponse(f"/manual/{txn_id}/edit?saved=1", status_code=303)


# ---------------------------------------------------------------------------
# 5.3 The flag route and the restore route
# ---------------------------------------------------------------------------


def _safe_next(value: str, fallback: str) -> str:
    """Return the next page. Accept only a path of this application."""
    target = (value or "").strip()
    if target.startswith("/") and not target.startswith("//"):
        return target
    return fallback


@router.post("/manual/{txn_id}/flag", include_in_schema=False)
def manual_flag(
    txn_id: str,
    next_url: str = Form("", alias="next"),
    db: Session = Depends(get_db),
):
    """Flag one hand-entered transaction for removal.

    The row stays in the database. The system refuses an imported transaction.
    """
    _get_manual_or_refuse(db, txn_id)
    flag_manual_transaction(db, txn_id)
    return RedirectResponse(
        _safe_next(next_url, "/manual/flagged"), status_code=303
    )


@router.post("/manual/{txn_id}/restore", include_in_schema=False)
def manual_restore(
    txn_id: str,
    next_url: str = Form("", alias="next"),
    db: Session = Depends(get_db),
):
    """Remove the removal flag from one hand-entered transaction."""
    _get_manual_or_refuse(db, txn_id)
    restore_manual_transaction(db, txn_id)
    return RedirectResponse(
        _safe_next(next_url, "/manual/flagged"), status_code=303
    )


# ---------------------------------------------------------------------------
# 5.4 The list of the flagged transactions, and 6.2 the purge
# ---------------------------------------------------------------------------


def _flagged_rows(db: Session) -> list[Transaction]:
    """Return each flagged transaction. The purge deletes exactly these rows."""
    return (
        db.query(Transaction)
        .filter(Transaction.deleted_at.isnot(None))
        .order_by(Transaction.transactiondate.desc())
        .all()
    )


def _render_flagged(
    request: Request,
    db: Session,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Show each flagged transaction, and the control of the purge."""
    ctx = {
        "request": request,
        "active_path": "/manual",
        "title": "The flagged transactions",
        "rows": _flagged_rows(db),
        "error": error,
        "purged": request.query_params.get("purged"),
    }
    return _templates(request).TemplateResponse(
        request, "manual_flagged.html", ctx, status_code=status_code
    )


@router.get("/manual/flagged", response_class=HTMLResponse, include_in_schema=False)
def manual_flagged_page(
    request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    """List each flagged transaction, so that the user checks it before the purge."""
    return _render_flagged(request, db)


@router.post("/manual/purge", include_in_schema=False)
def manual_purge(
    request: Request,
    confirm: str = Form(""),
    db: Session = Depends(get_db),
):
    """Delete each flagged transaction, and report the number of deleted rows.

    Caution: the application cannot undo the purge. The route therefore deletes
    nothing until the form holds the confirmation.
    """
    if confirm.strip().lower() not in CONFIRM_VALUES:
        logger.info("manual_purge_refused")
        return _render_flagged(
            request,
            db,
            error=(
                "Confirm the purge first. The system deleted no transaction."
            ),
            status_code=400,
        )
    db_path = request.app.state.settings.db_path
    count = purge_flagged_transactions(db, db_path)
    logger.info("manual_purge_ok", count=count)
    return RedirectResponse(f"/manual/flagged?purged={count}", status_code=303)
