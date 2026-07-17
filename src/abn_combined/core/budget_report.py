"""Budget-vs-actual aggregation (ported from abn-analyst ``routes/budgets.py``).

Actual spend uses the *effective* category (manual precedence:
``coalesce(nullif(manual_category, ''), category)``) with hierarchical prefix
matching (``food`` also matches ``food:restaurants`` and legacy ``food-...``),
summing ``abs(amount)`` inside the period window.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..constants import is_transfer_category
from .models import Budget, Transaction
from .utils import CATEGORY_SEPARATOR

PERIODS = ("year", "month", "week")


def get_period_dates(period: str, reference_date: date | None = None) -> tuple[date, date]:
    """Inclusive (start, end) window for the period containing ``reference_date``."""
    ref = reference_date or date.today()
    if period == "year":
        return date(ref.year, 1, 1), date(ref.year, 12, 31)
    if period == "month":
        start = date(ref.year, ref.month, 1)
        if ref.month == 12:
            end = date(ref.year, 12, 31)
        else:
            end = date(ref.year, ref.month + 1, 1) - timedelta(days=1)
        return start, end
    if period == "week":
        start = ref - timedelta(days=ref.weekday())  # Monday
        return start, start + timedelta(days=6)
    raise ValueError(f"Invalid period: {period}")


def _effective_category_expr():
    return func.coalesce(func.nullif(Transaction.manual_category, ""), Transaction.category)


def compute_actual(db: Session, category: str, period_start: date,
                   period_end: date, exclude_transfers: bool = True) -> float:
    """Total ``abs(amount)`` for the effective category (incl. children) in a window.

    Args:
        db: Database session
        category: Budget category to sum
        period_start: Inclusive start date
        period_end: Inclusive end date
        exclude_transfers: If True (default), exclude transfer transactions
    """
    eff = _effective_category_expr()
    c = category.strip().lower()
    query = db.query(func.sum(func.abs(Transaction.amount))).filter(
        Transaction.transactiondate >= period_start,
        Transaction.transactiondate <= period_end,
        or_(
            func.lower(eff) == c,
            func.lower(eff).like(f"{c}{CATEGORY_SEPARATOR}%"),
        ),
    )
    # Exclude transfers by default (unless exclude_transfers is False)
    if exclude_transfers:
        query = query.filter(
            or_(eff.is_(None), eff == "", ~eff.ilike('%transfer%'))
        )
    result = query.scalar()
    return float(result) if result is not None else 0.0


DEFAULT_AVERAGE_MONTHS = 3


def average_monthly_spend(db: Session, category: str, months: int = DEFAULT_AVERAGE_MONTHS,
                          reference_date: date | None = None,
                          exclude_transfers: bool = True) -> float:
    """Average monthly actual spend for ``category`` (incl. subtree) over the
    last ``months`` **full** calendar months before the month containing
    ``reference_date`` — the current in-progress month is deliberately
    excluded so a partial month never drags the average down. Used both to
    propose an amount when manually adding a budget and to seed the
    bulk "one budget per top-level category" action.
    """
    ref = reference_date or date.today()
    year, month = ref.year, ref.month
    total = 0.0
    for _ in range(months):
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
        start, end = get_period_dates("month", date(year, month, 1))
        total += compute_actual(db, category, start, end, exclude_transfers=exclude_transfers)
    return total / months if months else 0.0


def seed_amount_for_period(avg_monthly: float, period: str) -> float:
    """Proposed seed amount for a budget of ``period`` from an average monthly
    spend. Month/week seed at the monthly average as-is; year annualizes it
    (12 × monthly), rounded to 2dp — matching the seeded-budget contract."""
    if period == "year":
        return round(avg_monthly * 12, 2)
    return round(avg_monthly, 2)


def distinct_top_level_categories(db: Session) -> list[str]:
    """Distinct top-level (first-hyphen-segment) effective categories observed
    across transactions, sorted alphabetically — the same rollup convention
    Trends uses to group a full category value under its parent."""
    eff = _effective_category_expr()
    tops: set[str] = set()
    for (value,) in db.query(func.lower(eff)).distinct():
        if value:
            tops.add(value.split(CATEGORY_SEPARATOR, 1)[0])
    return sorted(tops)


def budget_status(actual: float, budget_amount: float) -> str:
    """'over' / 'near' (>= 80%) / 'under'."""
    amt = Decimal(str(budget_amount))
    act = Decimal(str(actual))
    if act > amt:
        return "over"
    if amt > 0 and act >= amt * Decimal("0.8"):
        return "near"
    return "under"


def budget_vs_actual_table(db: Session, reference_date: date | None = None,
                           period: str | None = None,
                           exclude_transfers: bool = True) -> list[dict]:
    """One row per valid budget with actuals for its current period window.

    Args:
        db: Database session
        reference_date: Reference date for period calculation (defaults to today)
        period: Restrict to budgets of one period type (year/month/week)
        exclude_transfers: If True (default), exclude transfer transactions from actuals

    ``period`` restricts to budgets of one period type; validity dates exclude
    budgets whose window does not overlap [start_date, end_date].
    """
    ref = reference_date or date.today()
    query = db.query(Budget)
    if period:
        query = query.filter(Budget.period == period)
    rows: list[dict] = []
    for budget in query.order_by(Budget.category).all():
        period_start, period_end = get_period_dates(budget.period, ref)
        if budget.start_date and period_end < budget.start_date:
            continue  # not yet active
        if budget.end_date and period_start > budget.end_date:
            continue  # expired
        actual = compute_actual(db, budget.category, period_start, period_end,
                               exclude_transfers=exclude_transfers)
        amount = float(budget.amount)
        rows.append(
            {
                "id": budget.id,
                "category": budget.category,
                "budget": amount,
                "actual": actual,
                "remaining": amount - actual,
                "percentage": round(actual / amount * 100, 1) if amount > 0 else 0.0,
                "status": budget_status(actual, amount),
                "period": budget.period,
                "period_start": period_start,
                "period_end": period_end,
                "start_date": budget.start_date,
                "end_date": budget.end_date,
                "notes": budget.notes,
            }
        )
    return rows
