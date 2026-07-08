"""Budgets page: CRUD + budget-vs-actual table for a selected period.

URL state: ``?period=<year|month|week>`` restricts the table to budgets of one
period type; ``?ref=YYYY-MM-DD`` picks the reference date whose containing
window is reported (defaults to today). Category cells link to the Transactions
view filtered to that category + period window.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..core.budget_report import PERIODS, budget_vs_actual_table
from ..core.filters import TransactionFilter
from ..core.models import Budget, CategorizationRule, Transaction
from ..core.utils import normalize_category
from ..db import get_db
from ..logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


def _templates(request: Request):
    from ..app import templates

    return templates


def _known_categories(db: Session) -> list[str]:
    cats: set[str] = set()
    for col in (Transaction.category, Transaction.manual_category,
                CategorizationRule.category):
        for (value,) in db.query(col).distinct():
            if value:
                cats.add(value.lower())
    return sorted(cats)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid date, use YYYY-MM-DD"
        ) from None


def _txn_link(category: str, period_start: date, period_end: date) -> str:
    f = TransactionFilter(categories=[category], date_from=period_start,
                          date_to=period_end)
    return f"/transactions?{f.to_query_string()}"


def _render(request: Request, db: Session, error: str | None = None) -> HTMLResponse:
    params = request.query_params
    period = params.get("period") or None
    if period not in PERIODS:
        period = None
    ref = _parse_date(params.get("ref")) or date.today()
    rows = budget_vs_actual_table(db, reference_date=ref, period=period)
    for row in rows:
        row["txn_url"] = _txn_link(row["category"], row["period_start"],
                                   row["period_end"])
    ctx = {
        "request": request,
        "active_path": "/budgets",
        "title": "Budgets",
        "rows": rows,
        "period": period,
        "periods": PERIODS,
        "ref": ref,
        "categories": _known_categories(db),
        "error": error,
    }
    return _templates(request).TemplateResponse(request, "budgets.html", ctx)


@router.get("/budgets", response_class=HTMLResponse, include_in_schema=False)
def budgets_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return _render(request, db)


def _parse_budget_form(category: str, amount: str, period: str,
                       start_date: str = "", end_date: str = "",
                       notes: str = "") -> dict:
    cat = normalize_category(category)
    if not cat:
        raise HTTPException(status_code=400, detail="Category is required")
    if period not in PERIODS:
        raise HTTPException(status_code=400,
                            detail="Period must be year, month or week")
    try:
        amt = Decimal(amount)
    except (InvalidOperation, TypeError):
        raise HTTPException(status_code=400, detail="Invalid amount") from None
    return {
        "category": cat,
        "amount": amt,
        "period": period,
        "start_date": _parse_date(start_date),
        "end_date": _parse_date(end_date),
        "notes": notes.strip() or None,
    }


@router.post("/budgets/create", include_in_schema=False)
def budget_create(request: Request, category: str = Form(...),
                  amount: str = Form(...), period: str = Form(...),
                  start_date: str = Form(""), end_date: str = Form(""),
                  notes: str = Form(""), db: Session = Depends(get_db)):
    data = _parse_budget_form(category, amount, period, start_date, end_date, notes)
    existing = (
        db.query(Budget)
        .filter(Budget.category == data["category"], Budget.period == data["period"])
        .first()
    )
    if existing:
        return _render(
            request, db,
            error=f"A {data['period']} budget for '{data['category']}' already exists.",
        )
    db.add(Budget(**data))
    db.commit()
    logger.info("budget_created", **{k: str(v) for k, v in data.items()})
    return RedirectResponse("/budgets", status_code=303)


def _get_budget_or_404(db: Session, budget_id: int) -> Budget:
    budget = db.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


@router.get("/budgets/{budget_id}/edit", response_class=HTMLResponse,
            include_in_schema=False)
def budget_edit_form(request: Request, budget_id: int,
                     db: Session = Depends(get_db)) -> HTMLResponse:
    budget = _get_budget_or_404(db, budget_id)
    ctx = {
        "request": request,
        "active_path": "/budgets",
        "title": "Edit budget",
        "budget": budget,
        "periods": PERIODS,
        "categories": _known_categories(db),
    }
    return _templates(request).TemplateResponse(request, "budgets_edit.html", ctx)


@router.post("/budgets/{budget_id}/update", include_in_schema=False)
def budget_update(request: Request, budget_id: int, category: str = Form(...),
                  amount: str = Form(...), period: str = Form(...),
                  start_date: str = Form(""), end_date: str = Form(""),
                  notes: str = Form(""), db: Session = Depends(get_db)):
    budget = _get_budget_or_404(db, budget_id)
    data = _parse_budget_form(category, amount, period, start_date, end_date, notes)
    duplicate = (
        db.query(Budget)
        .filter(Budget.category == data["category"], Budget.period == data["period"],
                Budget.id != budget_id)
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=400,
            detail=f"A {data['period']} budget for '{data['category']}' already exists.",
        )
    for key, value in data.items():
        setattr(budget, key, value)
    budget.updated_at = date.today()
    db.commit()
    logger.info("budget_updated", budget_id=budget_id)
    return RedirectResponse("/budgets", status_code=303)


@router.post("/budgets/{budget_id}/delete", include_in_schema=False)
def budget_delete(budget_id: int, db: Session = Depends(get_db)):
    budget = _get_budget_or_404(db, budget_id)
    db.delete(budget)
    db.commit()
    logger.info("budget_deleted", budget_id=budget_id)
    return RedirectResponse("/budgets", status_code=303)
