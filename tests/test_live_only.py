"""Tests for the shared `live_only` predicate (add-manual-transactions, 3.2-3.5).

A flagged transaction has a value in `deleted_at`. The user flagged the row for
removal, and only a purge deletes it. Seven readers must hide such a row. They
are the transactions list, the category trends, the cash flow, the budget
actuals, the tag usage counts, the match count of each rule, and the rule
preview.

Each reader builds its own query, so the exclusion lives in one predicate in
`core/filters.py`. `test_each_of_the_seven_readers_excludes_a_flagged_row`
walks the seven readers. It fails when a developer removes the predicate from
any one reader.

The two rows below have the exact shape that each reader accepts. Read the
comments beside the shape before you change a value. A wrong value makes a
reader skip the flagged row for a second reason, and the test then passes for
the wrong reason.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from abn_combined.api.rules import _matched_counts
from abn_combined.api.tags import collect_tags
from abn_combined.core.budget_report import average_monthly_spend, compute_actual
from abn_combined.core.cash_flow import compute_cash_flow
from abn_combined.core.categorizer import preview_rule
from abn_combined.core.filters import TransactionFilter, build_query, paginate
from abn_combined.core.models import Base, CategorizationRule, Transaction
from abn_combined.core.trends import TrendsParams, aggregate

# The window that every reader in this file receives.
WINDOW_FROM = date(2026, 3, 1)
WINDOW_TO = date(2026, 3, 31)
TXN_DATE = date(2026, 3, 10)
FLAG_TIME = datetime(2026, 3, 20, 9, 30, 0)

LIVE_AMOUNT = -30.0
FLAGGED_AMOUNT = -20.0

# The rule id that both rows carry in `categorization_source`.
RULE_ID = 1


@pytest.fixture
def db(tmp_path: Path) -> Session:
    """One empty SQLite database with the current schema."""
    engine = create_engine(f"sqlite:///{tmp_path / 'live_only.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _row(txn_id: str, amount: float, **kw) -> Transaction:
    """Build one transaction that each of the seven readers accepts.

    The values answer the pre-filter of each reader:
    - `category` is not a transfer category, so the transfer exclusion keeps it.
    - `manual_category` is empty, so the rule preview does not treat the row as
      a manual categorization.
    - `tags` holds one tag, so the tag usage counts read the row.
    - `categorization_source` holds the id of a real rule, so the match count of
      that rule reads the row.
    - `transactiondate` is inside the window of each reader.
    """
    values = dict(
        id=txn_id,
        accountNumber="NL01",
        transactiondate=TXN_DATE,
        amount=amount,
        currency="EUR",
        description="SPOTIFY PREMIUM",
        category="food",
        manual_category=None,
        tags="lunch",
        manual_tags=None,
        categorization_source=str(RULE_ID),
    )
    values.update(kw)
    return Transaction(**values)


@pytest.fixture
def seeded(db: Session) -> Session:
    """One live row and one flagged row, plus the rule that both point to."""
    db.add(
        CategorizationRule(
            id=RULE_ID,
            priority=100,
            rule_type="keyword",
            match_pattern="contains",
            field_target="description",
            match_value="spotify",
            category="food",
        )
    )
    db.add(_row("live1", LIVE_AMOUNT))
    db.add(
        _row(
            "flagged1",
            FLAGGED_AMOUNT,
            accountNumber="CASH",
            is_manual=True,
            deleted_at=FLAG_TIME,
        )
    )
    db.commit()
    return db


def _draft_rule() -> CategorizationRule:
    """A draft rule that matches the description of both rows."""
    return CategorizationRule(
        priority=100,
        rule_type="keyword",
        match_pattern="contains",
        field_target="description",
        match_value="spotify",
        category="music",
    )


# ---------------------------------------------------------------------------
# One measurement per reader
# ---------------------------------------------------------------------------


def _list_ids(db: Session) -> list[str]:
    """The ids that the transactions list shows."""
    f = TransactionFilter(date_from=WINDOW_FROM, date_to=WINDOW_TO)
    return sorted(t.id for t in build_query(db, f).all())


def _list_summary(db: Session) -> float:
    """The sum of the rows that the transactions list shows."""
    f = TransactionFilter(date_from=WINDOW_FROM, date_to=WINDOW_TO)
    page = paginate(db, f)
    return float(sum(float(t.amount) for t in page.items))


def _trends_total(db: Session) -> float:
    """The grand total of the category trends."""
    params = TrendsParams(date_from=WINDOW_FROM, date_to=WINDOW_TO)
    return aggregate(db, params).grand_total


def _cash_flow_expense(db: Session) -> float:
    """The total expense of the cash flow."""
    result = compute_cash_flow(db, WINDOW_FROM, WINDOW_TO)
    return result.total_expense


def _budget_actual(db: Session) -> float:
    """The actual spend of the budget category `food`."""
    return compute_actual(db, "food", WINDOW_FROM, WINDOW_TO)


def _tag_count(db: Session) -> int:
    """The usage count of the tag `lunch`."""
    for tag in collect_tags(db):
        if tag["name"] == "lunch":
            return tag["count"]
    return 0


def _rule_match_count(db: Session) -> int:
    """The match count of the one rule."""
    return _matched_counts(db).get(RULE_ID, 0)


def _preview_matches(db: Session) -> list[str]:
    """The ids that the rule preview reports as matched."""
    return sorted(preview_rule(db, _draft_rule()).matched)


# Eight measurements over the seven readers. The transactions list gives
# two of them, because task 3.2 asks for the rows and for the summary.
# reader name -> (measurement, the value that holds no flagged row)
READERS: dict[str, tuple] = {
    "transactions list": (_list_ids, ["live1"]),
    "transactions list summary": (_list_summary, LIVE_AMOUNT),
    "category trends": (_trends_total, LIVE_AMOUNT),
    "cash flow": (_cash_flow_expense, abs(LIVE_AMOUNT)),
    "budget actuals": (_budget_actual, abs(LIVE_AMOUNT)),
    "tag usage counts": (_tag_count, 1),
    "rule match count": (_rule_match_count, 1),
    "rule preview": (_preview_matches, ["live1"]),
}


# ---------------------------------------------------------------------------
# 3.5 The control: each of the seven readers hides a flagged row
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(READERS))
def test_each_of_the_seven_readers_excludes_a_flagged_row(seeded: Session, name: str):
    """Each reader reports the live row only.

    This test is the control for the shared predicate. It fails when a
    developer removes `live_only` from any one reader.
    """
    measure, expected = READERS[name]
    assert measure(seeded) == expected, f"the reader {name!r} reads a flagged row"


def test_the_flagged_row_stays_in_the_database(seeded: Session):
    """The flag hides the row. It does not delete the row."""
    row = seeded.get(Transaction, "flagged1")
    assert row is not None
    assert row.deleted_at == FLAG_TIME
    assert row.is_manual is True


def test_each_reader_reads_the_row_again_after_a_restore(seeded: Session):
    """The removal of the flag returns the row to each reader."""
    seeded.get(Transaction, "flagged1").deleted_at = None
    seeded.commit()
    assert _list_ids(seeded) == ["flagged1", "live1"]
    assert _trends_total(seeded) == LIVE_AMOUNT + FLAGGED_AMOUNT
    assert _cash_flow_expense(seeded) == abs(LIVE_AMOUNT) + abs(FLAGGED_AMOUNT)
    assert _budget_actual(seeded) == abs(LIVE_AMOUNT) + abs(FLAGGED_AMOUNT)
    assert _tag_count(seeded) == 2
    assert _rule_match_count(seeded) == 2
    assert _preview_matches(seeded) == ["flagged1", "live1"]


# ---------------------------------------------------------------------------
# 3.2 The transactions list and its summary
# ---------------------------------------------------------------------------


def test_the_transactions_list_holds_no_flagged_row(seeded: Session):
    f = TransactionFilter(date_from=WINDOW_FROM, date_to=WINDOW_TO)
    page = paginate(seeded, f)
    assert page.total == 1
    assert [t.id for t in page.items] == ["live1"]


def test_the_summary_of_the_transactions_list_holds_no_flagged_row(seeded: Session):
    assert _list_summary(seeded) == LIVE_AMOUNT


# ---------------------------------------------------------------------------
# 3.3 The three aggregations
# ---------------------------------------------------------------------------


def test_a_flagged_row_adds_nothing_to_a_trends_cell(seeded: Session):
    table = aggregate(seeded, TrendsParams(date_from=WINDOW_FROM, date_to=WINDOW_TO))
    assert table.grand_total == LIVE_AMOUNT
    assert table.column_totals == {"2026-03": LIVE_AMOUNT}
    assert [row.label for row in table.rows] == ["food"]
    assert table.rows[0].cells == {"2026-03": LIVE_AMOUNT}


def test_a_flagged_row_adds_nothing_to_a_cash_flow_cell(seeded: Session):
    result = compute_cash_flow(seeded, WINDOW_FROM, WINDOW_TO)
    assert result.expense == [abs(LIVE_AMOUNT)]
    assert result.total_expense == abs(LIVE_AMOUNT)
    assert result.total_income == 0.0


def test_a_flagged_row_adds_nothing_to_a_budget_actual(seeded: Session):
    assert compute_actual(seeded, "food", WINDOW_FROM, WINDOW_TO) == abs(LIVE_AMOUNT)


def test_a_flagged_row_adds_nothing_to_an_average_monthly_spend(seeded: Session):
    """`average_monthly_spend` calls `compute_actual`, so it inherits the rule."""
    average = average_monthly_spend(
        seeded, "food", months=1, reference_date=date(2026, 4, 15)
    )
    assert average == abs(LIVE_AMOUNT)


# ---------------------------------------------------------------------------
# 3.4 The three counts
# ---------------------------------------------------------------------------


def test_the_tag_usage_counts_count_no_flagged_row(seeded: Session):
    tags = collect_tags(seeded)
    assert [(t["name"], t["count"]) for t in tags] == [("lunch", 1)]
    assert tags[0]["debit_amount"] == abs(LIVE_AMOUNT)


def test_the_match_count_of_a_rule_counts_no_flagged_row(seeded: Session):
    assert _matched_counts(seeded) == {RULE_ID: 1}


def test_the_rule_preview_counts_no_flagged_row(seeded: Session):
    result = preview_rule(seeded, _draft_rule())
    assert result.matched == ["live1"]
    assert result.gains == ["live1"]
    assert [change.transaction_id for change in result.changes] == ["live1"]
