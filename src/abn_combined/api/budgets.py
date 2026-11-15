"""Budgets page: CRUD + budget-vs-actual table for a selected period.

URL state: ``?period=<year|month>`` selects the tab. ``?month=YYYY-MM`` (Monthly
tab) or ``?year=YYYY`` (Yearly tab) selects the reported window; the default is
the current month or year. An old ``?ref=YYYY-MM-DD`` link selects the month or
year that holds that date. ``?sort=<column>_<asc|desc>`` sorts the table.
Category cells link to the Transactions view filtered to that category + window.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.budget_report import (
    DEFAULT_AVERAGE_MONTHS,
    PERIODS,
    SEED_EXCLUDED_CATEGORIES,
    average_monthly_spend,
    budget_vs_actual_table,
    check_validity_bounds,
    describe_budget,
    distinct_top_level_categories,
    find_overlap,
    get_period_dates,
    seed_amount_for_period,
    seed_budgets,
    valid_budget_on,
)
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


# The tabs of the page. The week period has no tab (see design).
TABS = ("month", "year")

# Sort keys of the budget table: column -> key function over a report row.
_STATUS_ORDER = {"over": 0, "near": 1, "under": 2}
_SORT_KEYS = {
    "category": lambda r: r["category"],
    "period": lambda r: r["period"],
    "window": lambda r: r["period_start"],
    "budget": lambda r: r["budget"],
    "actual": lambda r: r["actual"],
    "remaining": lambda r: r["remaining"],
    "used": lambda r: r["percentage"],
    "status": lambda r: _STATUS_ORDER.get(r["status"], 3),
}
DEFAULT_BUDGET_SORT = "budget_desc"


def _parse_sort(value: str | None) -> tuple[str, bool]:
    """Return ``(column, descending)``; an unknown value gives the default."""
    column, _, direction = (value or "").rpartition("_")
    if column not in _SORT_KEYS or direction not in ("asc", "desc"):
        column, _, direction = DEFAULT_BUDGET_SORT.rpartition("_")
    return column, direction == "desc"


def _sort_rows(rows: list[dict], sort: str | None) -> list[dict]:
    """Sort on the selected column. Equal values keep the category order."""
    column, descending = _parse_sort(sort)
    by_category = sorted(rows, key=lambda r: r["category"])
    return sorted(by_category, key=_SORT_KEYS[column], reverse=descending)


def _next_sort(current: str | None, column: str) -> str:
    """A click on a header sorts ascending, and a second click reverses."""
    cur_column, descending = _parse_sort(current)
    if cur_column == column and not descending:
        return f"{column}_desc"
    return f"{column}_asc"


def _parse_selection(params, period: str) -> date:
    """Return the first day of the selected month or year (400 if malformed)."""
    today = date.today()
    raw = params.get(period)
    if raw:
        pattern = r"\d{4}-\d{2}" if period == "month" else r"\d{4}"
        if not re.fullmatch(pattern, raw):
            raise HTTPException(status_code=400, detail=f"Invalid {period}, use "
                                + ("YYYY-MM" if period == "month" else "YYYY"))
        try:
            ref = date.fromisoformat(f"{raw}-01" if period == "month" else f"{raw}-01-01")
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid {period}") from None
    else:
        ref = _parse_date(params.get("ref")) or today
    return get_period_dates(period, ref)[0]


def _selection_params(period: str, start: date) -> dict[str, str]:
    if period == "year":
        return {"period": "year", "year": str(start.year)}
    return {"period": "month", "month": start.strftime("%Y-%m")}


def _year_options(db: Session, selected: int) -> list[int]:
    """Years with transactions or budgets, the current year, the next year."""
    years = {date.today().year, date.today().year + 1, selected}
    low = db.query(func.min(Transaction.transactiondate)).scalar()
    if low is not None:
        years.update(range(low.year, date.today().year + 1))
    for (start,) in db.query(Budget.start_date).filter(Budget.start_date.isnot(None)):
        years.add(start.year)
    return sorted(years)


def _render(request: Request, db: Session, error: str | None = None) -> HTMLResponse:
    params = request.query_params
    # Monthly / Yearly tabs drive ``?period=``; default to month (not "All")
    # when absent so the page always opens on a concrete tab.
    period = params.get("period") or "month"
    if period not in TABS:
        period = "month"
    start = _parse_selection(params, period)
    sort = params.get("sort") or DEFAULT_BUDGET_SORT
    rows = _sort_rows(budget_vs_actual_table(db, reference_date=start, period=period), sort)
    for row in rows:
        row["txn_url"] = _txn_link(row["category"], row["period_start"],
                                   row["period_end"])
    selection = _selection_params(period, start)
    today = date.today()
    # Switching the tab keeps the selection where it applies.
    month_for_tab = start if period == "month" else (
        date(today.year, today.month, 1) if start.year == today.year else start)
    sort_column, sort_desc = _parse_sort(sort)
    # "Valid from" on the Add form follows the active tab; the budget repeats.
    add_start, _ = get_period_dates(period, today)
    ctx = {
        "request": request,
        "active_path": "/budgets",
        "title": "Budgets",
        "rows": rows,
        "period": period,
        "periods": PERIODS,
        "selected_month": start.strftime("%Y-%m"),
        "selected_year": start.year,
        "year_options": _year_options(db, start.year),
        "month_tab_url": "/budgets?" + urlencode(_selection_params("month", month_for_tab)),
        "year_tab_url": "/budgets?" + urlencode(_selection_params("year", start)),
        "seed_url": "/budgets/seed?" + urlencode(
            {"period": period, "start": selection[period]}),
        "sort_column": sort_column,
        "sort_desc": sort_desc,
        "sort_url": lambda column: "/budgets?" + urlencode(
            {**selection, "sort": _next_sort(sort, column)}),
        "categories": _known_categories(db),
        "error": error,
        "current_period_start": add_start,
        "average_months": DEFAULT_AVERAGE_MONTHS,
    }
    return _templates(request).TemplateResponse(request, "budgets.html", ctx)


@router.get("/budgets", response_class=HTMLResponse, include_in_schema=False)
def budgets_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return _render(request, db)


@router.get("/budgets/average-hint", response_class=HTMLResponse, include_in_schema=False)
def budget_average_hint(category: str = "", db: Session = Depends(get_db)) -> HTMLResponse:
    """Small htmx-triggered fragment shown below the Amount field on the "Add
    budget" form — the average monthly actual spend for whatever category is
    currently typed in, so the user has a concrete number to anchor the
    manual amount against."""
    cat = normalize_category(category)
    if not cat:
        return HTMLResponse("")
    avg = average_monthly_spend(db, cat)
    if avg <= 0:
        return HTMLResponse(
            '<small class="text-muted">No recent spend for this category.</small>'
        )
    return HTMLResponse(
        f'<small class="text-muted">Recent average: {avg:.2f} '
        f"(last {DEFAULT_AVERAGE_MONTHS} months)</small>"
    )


def _parse_seed_start(period: str, raw: str | None) -> date:
    """First day of the seed start month (``YYYY-MM``) or year (``YYYY``)."""
    return _parse_selection({period: raw} if raw else {}, period)


def _seed_rows(db: Session, period: str, start: date) -> list[dict]:
    """One row for each top-level category with recent spend, for the dialog."""
    rows = []
    for cat in distinct_top_level_categories(db):
        if cat in SEED_EXCLUDED_CATEGORIES:
            continue
        avg = average_monthly_spend(db, cat, reference_date=date.today())
        if avg <= 0:
            continue
        current = valid_budget_on(db, cat, period, start)
        rows.append({
            "category": cat,
            "amount": seed_amount_for_period(avg, period),
            "current": current,
            "selected": current is None,
        })
    return rows


@router.get("/budgets/seed", response_class=HTMLResponse, include_in_schema=False)
def budgets_seed_dialog(request: Request, period: str = "month", start: str = "",
                        db: Session = Depends(get_db)) -> HTMLResponse:
    """The dialog of the seed action. It writes nothing: the user selects the
    start month or year, and the categories to create or to override."""
    if period not in TABS:
        period = "month"
    first = _parse_seed_start(period, start)
    ctx = {
        "request": request,
        "active_path": "/budgets",
        "title": "Create budgets",
        "period": period,
        "start": first,
        "start_value": _selection_params(period, first)[period],
        "year_options": _year_options(db, first.year),
        "rows": _seed_rows(db, period, first),
        "average_months": DEFAULT_AVERAGE_MONTHS,
        "back_url": "/budgets?" + urlencode(_selection_params(period, first)),
    }
    return _templates(request).TemplateResponse(request, "budgets_seed.html", ctx)


@router.post("/budgets/seed", include_in_schema=False)
async def budgets_seed_apply(request: Request, db: Session = Depends(get_db)):
    """Create or override a budget from the start for each selected category,
    with the amount from the dialog. See ``budget_report.seed_budgets``."""
    form = await request.form()
    period = form.get("period") or "month"
    if period not in TABS:
        period = "month"
    first = _parse_seed_start(period, form.get("start"))
    selected = set(form.getlist("selected"))
    choices: list[tuple[str, float]] = []
    for cat, raw in zip(form.getlist("row_category"), form.getlist("row_amount"),
                        strict=False):
        if cat not in selected:
            continue
        try:
            amount = float(Decimal(raw))
        except (InvalidOperation, TypeError):
            raise HTTPException(status_code=400,
                                detail=f"Invalid amount for '{cat}'") from None
        choices.append((cat, amount))
    notes = (
        f"Auto-created from {DEFAULT_AVERAGE_MONTHS}-month average"
        + (" (annualized)" if period == "year" else "")
    )
    result = seed_budgets(db, period, first, choices, notes)
    logger.info("budgets_seeded", period=period, start=first.isoformat(), **result)
    return RedirectResponse(
        "/budgets?" + urlencode(_selection_params(period, first)), status_code=303
    )


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
    data = {
        "category": cat,
        "amount": amt,
        "period": period,
        "start_date": _parse_date(start_date),
        "end_date": _parse_date(end_date),
        "notes": notes.strip() or None,
    }
    bounds_error = check_validity_bounds(period, data["start_date"], data["end_date"])
    if bounds_error:
        raise HTTPException(status_code=400, detail=bounds_error)
    return data


@router.post("/budgets/create", include_in_schema=False)
def budget_create(request: Request, category: str = Form(...),
                  amount: str = Form(...), period: str = Form(...),
                  start_date: str = Form(""), end_date: str = Form(""),
                  notes: str = Form(""), db: Session = Depends(get_db)):
    data = _parse_budget_form(category, amount, period, start_date, end_date, notes)
    existing = find_overlap(db, data["category"], data["period"],
                            data["start_date"], data["end_date"])
    if existing:
        return _render(
            request, db,
            error=f"The new budget overlaps {describe_budget(existing)}. "
                  "End that budget first, or use Create budgets to override it.",
        )
    db.add(Budget(**data))
    db.commit()
    logger.info("budget_created", **{k: str(v) for k, v in data.items()})
    return RedirectResponse(f"/budgets?period={data['period']}", status_code=303)


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
    duplicate = find_overlap(db, data["category"], data["period"],
                             data["start_date"], data["end_date"], exclude_id=budget_id)
    if duplicate:
        raise HTTPException(
            status_code=400,
            detail=f"The budget overlaps {describe_budget(duplicate)}.",
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
