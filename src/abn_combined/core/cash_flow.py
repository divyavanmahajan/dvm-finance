"""Cash-flow aggregation: income vs expense per period, table form.

Ported (simplified per spec FR6.2 — no charts, no section hierarchy) from
abn-analyst ``routes/cash_flow.py``. Aggregation runs as a single SQL GROUP BY
(NFR2), bucketing by month (default), week (Monday-start) or year.

Semantics kept from the legacy code:
- Effective category = manual precedence.
- Transactions whose effective category contains "transfer" are excluded
  (transfers between own accounts are not income or expense).
- Income = sum of positive amounts, Expense = sum of abs(negative amounts).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import case, func, not_, or_
from sqlalchemy.orm import Session

from .models import Transaction

BREAKDOWNS = ("month", "week", "year")


# ---------------------------------------------------------------------------
# Period generation
# ---------------------------------------------------------------------------


def _month_add(d: date, months: int = 1) -> date:
    year, month = d.year, d.month + months
    while month > 12:
        year, month = year + 1, month - 12
    return date(year, month, 1)


def generate_periods(start_date: date, end_date: date,
                     breakdown: str) -> list[tuple[date, date, str]]:
    """(start, end, label) tuples covering [start_date, end_date]."""
    periods: list[tuple[date, date, str]] = []
    if breakdown == "week":
        current = start_date - timedelta(days=start_date.weekday())  # Monday
        while current <= end_date:
            period_end = min(current + timedelta(days=6), end_date)
            label = current.strftime("%b %d, %Y") if current.year != period_end.year \
                else current.strftime("%b %d")
            periods.append((current, period_end, label))
            current = current + timedelta(days=7)
    elif breakdown == "month":
        current = start_date.replace(day=1)
        while current <= end_date:
            nxt = _month_add(current)
            periods.append((current, min(nxt - timedelta(days=1), end_date),
                            current.strftime("%b %Y")))
            current = nxt
    elif breakdown == "year":
        current = start_date.replace(month=1, day=1)
        while current <= end_date:
            periods.append((current, min(date(current.year, 12, 31), end_date),
                            str(current.year)))
            current = date(current.year + 1, 1, 1)
    else:
        raise ValueError(f"Invalid breakdown: {breakdown}")
    return periods


def _bucket_key(d: date, breakdown: str) -> str:
    if breakdown == "month":
        return d.strftime("%Y-%m")
    if breakdown == "year":
        return d.strftime("%Y")
    # week: Monday ISO date
    return (d - timedelta(days=d.weekday())).isoformat()


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


@dataclass
class CashFlowResult:
    """Per-period income/expense/net plus overall totals."""

    periods: list[tuple[date, date, str]] = field(default_factory=list)
    income: list[float] = field(default_factory=list)
    expense: list[float] = field(default_factory=list)

    @property
    def net(self) -> list[float]:
        return [i - e for i, e in zip(self.income, self.expense, strict=True)]

    @property
    def total_income(self) -> float:
        return sum(self.income)

    @property
    def total_expense(self) -> float:
        return sum(self.expense)

    @property
    def total_net(self) -> float:
        return self.total_income - self.total_expense


def compute_cash_flow(db: Session, date_from: date, date_to: date,
                      breakdown: str = "month",
                      accounts: list[str] | None = None) -> CashFlowResult:
    """Aggregate income vs expense per period via a single SQL GROUP BY."""
    if breakdown not in BREAKDOWNS:
        raise ValueError(f"Invalid breakdown: {breakdown}")

    eff = func.lower(
        func.coalesce(func.nullif(Transaction.manual_category, ""), Transaction.category)
    )
    if breakdown == "month":
        bucket = func.strftime("%Y-%m", Transaction.transactiondate)
    elif breakdown == "year":
        bucket = func.strftime("%Y", Transaction.transactiondate)
    else:  # week -> Monday of the ISO week
        bucket = func.date(Transaction.transactiondate, "-6 days", "weekday 1")

    income_sum = func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0))
    expense_sum = func.sum(
        case((Transaction.amount < 0, -Transaction.amount), else_=0)
    )

    query = (
        db.query(bucket.label("bucket"), income_sum.label("income"),
                 expense_sum.label("expense"))
        .filter(
            Transaction.transactiondate >= date_from,
            Transaction.transactiondate <= date_to,
            # Exclude transfers by effective category (legacy semantics).
            or_(eff.is_(None), not_(eff.like("%transfer%"))),
        )
    )
    if accounts:
        query = query.filter(Transaction.accountNumber.in_(accounts))
    rows = {r.bucket: r for r in query.group_by("bucket").all()}

    periods = generate_periods(date_from, date_to, breakdown)
    result = CashFlowResult(periods=periods)
    for p_start, _p_end, _label in periods:
        row = rows.get(_bucket_key(p_start, breakdown))
        result.income.append(float(row.income or 0) if row else 0.0)
        result.expense.append(float(row.expense or 0) if row else 0.0)
    return result
