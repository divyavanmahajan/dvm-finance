"""Cash flow page: income vs expense per period with a net row (table, no charts).

URL state (Golden Principle 8): ``?date_from=&date_to=&preset=&breakdown=&account=``.
Defaults to the current year by month. Period amounts link to the Transactions
view filtered to the period window (+ account). The filter model only supports
``abs(amount)`` ranges, so income/expense links cannot carry a sign filter —
they link to all of the period's transactions (documented deviation).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..core.cash_flow import BREAKDOWNS, compute_cash_flow
from ..core.filters import PRESETS, TransactionFilter, resolve_preset_range
from ..core.models import Transaction
from ..db import get_db
from ..logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


def _templates(request: Request):
    from ..app import templates

    return templates


def _known_accounts(db: Session) -> list[str]:
    rows = db.query(Transaction.accountNumber).distinct().all()
    return sorted({r[0] for r in rows if r[0]})


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _txn_link(p_start: date, p_end: date, accounts: list[str]) -> str:
    f = TransactionFilter(date_from=p_start, date_to=p_end, accounts=accounts)
    return f"/transactions?{f.to_query_string()}"


def _cash_flow_context(request: Request, db: Session) -> dict:
    params = request.query_params
    breakdown = params.get("breakdown") or "month"
    if breakdown not in BREAKDOWNS:
        breakdown = "month"
    preset = params.get("preset") or None
    if preset not in PRESETS:
        preset = None
    accounts = [a for a in params.getlist("account") if a]
    # Parse include_transfers: True if param is "1", "true", or "True"; False otherwise
    include_transfers_str = params.get("include_transfers") or ""
    include_transfers = include_transfers_str in ("1", "true", "True")

    today = date.today()
    if preset:
        date_from, date_to = resolve_preset_range(preset, today)
    else:
        date_from = _parse_date(params.get("date_from")) or date(today.year, 1, 1)
        date_to = _parse_date(params.get("date_to")) or date(today.year, 12, 31)

    result = compute_cash_flow(db, date_from=date_from, date_to=date_to,
                               breakdown=breakdown, accounts=accounts or None,
                               include_transfers=include_transfers)
    columns = [
        {
            "label": label,
            "income": result.income[i],
            "expense": result.expense[i],
            "net": result.net[i],
            "txn_url": _txn_link(p_start, p_end, accounts),
        }
        for i, (p_start, p_end, label) in enumerate(result.periods)
    ]
    return {
        "request": request,
        "active_path": "/cash-flow",
        "title": "Cash Flow",
        "columns": columns,
        "result": result,
        "breakdown": breakdown,
        "breakdowns": BREAKDOWNS,
        "preset": preset,
        "presets": PRESETS,
        "date_from": date_from,
        "date_to": date_to,
        "accounts": accounts,
        "known_accounts": _known_accounts(db),
        "total_txn_url": _txn_link(date_from, date_to, accounts),
        "include_transfers": include_transfers,
    }


@router.get("/cash-flow", response_class=HTMLResponse, include_in_schema=False)
def cash_flow_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    ctx = _cash_flow_context(request, db)
    return _templates(request).TemplateResponse(request, "cash_flow.html", ctx)


@router.get("/cash-flow/table", response_class=HTMLResponse, include_in_schema=False)
def cash_flow_table(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    ctx = _cash_flow_context(request, db)
    return _templates(request).TemplateResponse(request, "_cash_flow_table.html", ctx)
