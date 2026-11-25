"""Fictional sample dataset for a new user of the web app.

Port of ``ios/DVMFinanceKit/Sources/DVMFinanceKit/Query/SampleDataset.swift``.
This is the one unit where Python follows Swift: the iOS app had the dataset
first. Both apps must produce the same rows for the same day, and a parity test
in each language holds the same values.

Rules of the set:
- The load adds rows and never deletes a row. The data of the user stays.
- Each sample transaction id starts with ``ID_PREFIX``. An imported row has a
  content-derived hash id, and a hand-entered row has a UUID, so no real row
  can start with this prefix.
- Each sample budget carries ``BUDGET_NOTE`` in ``notes``. The load skips a
  sample budget when the user has a budget with the same category and period.
- The removal deletes only the rows that these two marks identify.
- The load does not run the rules, so it writes no rule change report.
- The snapshot export refuses to run while the set is present.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from .budget_report import get_period_dates
from .models import Budget, Transaction

ID_PREFIX = "sample-"
BUDGET_NOTE = "Sample budget"
ACCOUNT_NUMBER = "NL91ABNA0417164300"
CATEGORIZATION_SOURCE = "sample"


@dataclass(frozen=True)
class Counts:
    """The numbers of rows that a load added or a removal deleted."""

    transactions: int
    budgets: int


# One recurring monthly line item: the day of the month, the category, the
# description, and the amount (negative = spend, positive = income).
_MONTHLY: list[tuple[int, str, str, float]] = [
    (25, "income", "Salary — Acme BV", 3250.00),
    (2, "groceries", "Albert Heijn", -42.18),
    (9, "groceries", "Jumbo Supermarkt", -56.73),
    (17, "groceries", "Marqt", -47.32),
    (4, "dining", "Cafe De Jaren", -28.50),
    (14, "dining", "Restaurant Bloem", -68.00),
    (21, "dining", "Thuisbezorgd", -31.20),
    (6, "transport", "NS Reizigers", -19.40),
    (19, "transport", "Shell Fuel", -72.10),
    (8, "utilities", "Vattenfall Energy", -87.65),
    (22, "utilities", "Ziggo Internet", -49.00),
    (12, "subscriptions", "Netflix", -13.99),
    (12, "subscriptions", "Spotify Premium", -10.99),
    (5, "entertainment", "Pathe Cinema", -24.00),
    (16, "shopping", "Bol.com Order", -64.99),
    (18, "health", "Apotheek", -22.45),
]

_MONTHLY_BUDGETS: list[tuple[str, int]] = [("groceries", 250), ("dining", 150), ("transport", 120)]
_YEARLY_BUDGETS: list[tuple[str, int]] = [("shopping", 1500), ("subscriptions", 360)]


def _sample_transactions(db: Session):
    return db.query(Transaction).filter(Transaction.id.like(f"{ID_PREFIX}%"))


def _sample_budgets(db: Session):
    return db.query(Budget).filter(Budget.notes == BUDGET_NOTE)


def is_loaded(db: Session) -> bool:
    """``True`` when the database holds a sample transaction or a sample budget."""
    return (
        _sample_transactions(db).first() is not None
        or _sample_budgets(db).first() is not None
    )


def is_database_empty(db: Session) -> bool:
    """``True`` when the database holds no live transaction.

    A live transaction is not soft-deleted and not merged into another row.
    """
    live = db.query(Transaction.id).filter(
        Transaction.deleted_at.is_(None), Transaction.merged_into.is_(None)
    )
    return live.first() is None


def _month_start(year: int, month: int, months_ago: int) -> date:
    index = year * 12 + (month - 1) - months_ago
    return date(index // 12, index % 12 + 1, 1)


def load(db: Session, today: date | None = None) -> Counts:
    """Add the sample set and commit. Each date falls in the 12 months up to
    ``today``, and the load skips a day after ``today``. When the set is
    already present, the load adds nothing and returns zero counts.
    """
    if is_loaded(db):
        return Counts(transactions=0, budgets=0)
    day = today or date.today()

    sequence = 0
    for months_ago in range(12):
        month_start = _month_start(day.year, day.month, months_ago)
        # A small fixed variation, so that the months are not identical.
        wobble = 1.0 + ((months_ago * 7) % 11 - 5) / 100.0
        for item_day, category, description, amount in _MONTHLY:
            txn_date = month_start + timedelta(days=item_day - 1)
            if txn_date > day:
                continue
            value = amount if category == "income" else amount * wobble
            db.add(
                Transaction(
                    id=f"{ID_PREFIX}{sequence}",
                    accountNumber=ACCOUNT_NUMBER,
                    transactiondate=txn_date,
                    amount=Decimal(f"{value:.2f}"),
                    description=description,
                    category=category,
                    categorization_source=CATEGORIZATION_SOURCE,
                    currency="EUR",
                )
            )
            sequence += 1

    budgets = 0
    for period, items in (("month", _MONTHLY_BUDGETS), ("year", _YEARLY_BUDGETS)):
        start, end = get_period_dates(period, day)
        for category, amount in items:
            if _budget_exists(db, category, period):
                continue
            db.add(
                Budget(
                    category=category,
                    amount=Decimal(amount),
                    period=period,
                    start_date=start,
                    end_date=end,
                    notes=BUDGET_NOTE,
                    created_at=day,
                    updated_at=day,
                )
            )
            budgets += 1

    db.commit()
    return Counts(transactions=sequence, budgets=budgets)


def remove(db: Session) -> Counts:
    """Delete each sample transaction and each sample budget, and commit.

    The removal does not touch another row.
    """
    transactions = _sample_transactions(db).delete(synchronize_session=False)
    budgets = _sample_budgets(db).delete(synchronize_session=False)
    db.commit()
    return Counts(transactions=transactions, budgets=budgets)


def _budget_exists(db: Session, category: str, period: str) -> bool:
    return (
        db.query(Budget.id)
        .filter(Budget.category == category, Budget.period == period)
        .first()
        is not None
    )
