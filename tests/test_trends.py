"""Unit tests for the category-trends aggregation (core/trends.py).

Covers: default window, period generation (month boundaries + window clamping),
manual-category precedence, uncategorized bucket, hyphen-hierarchy rollup
(the separator convention found in the legacy abn_analyst.db), row/column/grand
totals, year granularity, account filter, and click-through link building.
"""

from __future__ import annotations

from datetime import date

import pytest

from abn_combined.core.models import Transaction
from abn_combined.core.trends import (
    SEPARATOR,
    TrendsParams,
    aggregate,
    build_periods,
    default_window,
    transactions_link,
)
from abn_combined.db import get_session_factory


def _mk(**kw) -> Transaction:
    base = dict(
        accountNumber="NL01",
        transactiondate=date(2024, 1, 15),
        amount=-10.0,
        currency="EUR",
        description="Test transaction",
    )
    base.update(kw)
    base.setdefault(
        "id",
        f"{base['accountNumber']}-{base['transactiondate']}-{base['amount']}-{base['description']}",
    )
    return Transaction(**base)


@pytest.fixture
def db(app):
    factory = get_session_factory()
    session = factory()
    yield session
    session.close()


def _seed(db, txns):
    for t in txns:
        db.add(t)
    db.commit()


def _row(table, label):
    for row in table.rows:
        if row.label == label:
            return row
    raise AssertionError(f"row {label!r} not in {[r.label for r in table.rows]}")


def _child(row, label):
    for child in row.children:
        if child.label == label:
            return child
    raise AssertionError(f"child {label!r} not in {[c.label for c in row.children]}")


# ---------------------------------------------------------------------------
# Window / periods
# ---------------------------------------------------------------------------


def test_separator_is_hyphen():
    # Convention confirmed against the legacy abn_analyst.db (groceries-ah, ...)
    assert SEPARATOR == "-"


def test_default_window_last_12_months_ends_today():
    """The current in-progress month must be included, not just complete
    months — a user opening Trends expects to see this month's spending
    so far."""
    lo, hi = default_window(today=date(2026, 7, 7))
    assert lo == date(2025, 8, 1)
    assert hi == date(2026, 7, 7)


def test_default_window_january():
    lo, hi = default_window(today=date(2026, 1, 15))
    assert lo == date(2025, 2, 1)
    assert hi == date(2026, 1, 15)


def test_build_periods_month():
    periods = build_periods(date(2024, 1, 1), date(2024, 3, 31), "month")
    assert [p.key for p in periods] == ["2024-01", "2024-02", "2024-03"]
    assert periods[0].start == date(2024, 1, 1)
    assert periods[0].end == date(2024, 1, 31)
    assert periods[1].end == date(2024, 2, 29)  # leap year
    assert periods[0].label == "Jan 2024"


def test_build_periods_clamped_to_window():
    # A window starting/ending mid-month clamps the first/last period so that
    # the cell link's date range never exceeds the aggregated range.
    periods = build_periods(date(2024, 1, 10), date(2024, 2, 20), "month")
    assert periods[0].start == date(2024, 1, 10)
    assert periods[0].end == date(2024, 1, 31)
    assert periods[-1].start == date(2024, 2, 1)
    assert periods[-1].end == date(2024, 2, 20)


def test_build_periods_year_clamped():
    periods = build_periods(date(2025, 7, 1), date(2026, 6, 30), "year")
    assert [p.key for p in periods] == ["2025", "2026"]
    assert periods[0].start == date(2025, 7, 1)
    assert periods[0].end == date(2025, 12, 31)
    assert periods[1].start == date(2026, 1, 1)
    assert periods[1].end == date(2026, 6, 30)
    assert periods[0].label == "2025"


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _params(**kw) -> TrendsParams:
    kw.setdefault("date_from", date(2024, 1, 1))
    kw.setdefault("date_to", date(2024, 12, 31))
    return TrendsParams(**kw)


def test_month_boundaries(db):
    _seed(db, [
        _mk(id="a", transactiondate=date(2024, 1, 31), amount=-10.0, category="dining"),
        _mk(id="b", transactiondate=date(2024, 2, 1), amount=-20.0, category="dining"),
    ])
    table = aggregate(db, _params(date_to=date(2024, 2, 29)))
    row = _row(table, "dining")
    assert row.cells["2024-01"] == pytest.approx(-10.0)
    assert row.cells["2024-02"] == pytest.approx(-20.0)
    assert row.total == pytest.approx(-30.0)


def test_manual_category_precedence(db):
    _seed(db, [
        _mk(id="a", category="dining", manual_category="groceries", amount=-5.0),
        _mk(id="b", category="dining", amount=-7.0),
    ])
    table = aggregate(db, _params())
    assert _row(table, "groceries").total == pytest.approx(-5.0)
    assert _row(table, "dining").total == pytest.approx(-7.0)


def test_empty_manual_category_falls_back(db):
    _seed(db, [_mk(id="a", category="dining", manual_category="", amount=-5.0)])
    table = aggregate(db, _params())
    assert _row(table, "dining").total == pytest.approx(-5.0)


def test_uncategorized_bucket(db):
    _seed(db, [
        _mk(id="a", category=None, amount=-3.0),
        _mk(id="b", category="", amount=-4.0),
        _mk(id="c", category="dining", amount=-9.0),
    ])
    table = aggregate(db, _params())
    unc = _row(table, "Uncategorized")
    assert unc.total == pytest.approx(-7.0)
    assert unc.categories == ["uncategorized"]
    # Uncategorized is the last row
    assert table.rows[-1].label == "Uncategorized"


def test_hierarchy_rollup(db):
    _seed(db, [
        _mk(id="a", category="groceries-ah", amount=-10.0,
            transactiondate=date(2024, 1, 5)),
        _mk(id="b", category="groceries-jumbo", amount=-20.0,
            transactiondate=date(2024, 1, 6)),
        _mk(id="c", category="groceries", amount=-5.0,
            transactiondate=date(2024, 2, 6)),
        _mk(id="d", category="salary", amount=1000.0, transactiondate=date(2024, 1, 25)),
    ])
    table = aggregate(db, _params())

    parent = _row(table, "groceries")
    assert parent.has_children
    assert parent.total == pytest.approx(-35.0)
    assert parent.cells["2024-01"] == pytest.approx(-30.0)
    assert parent.cells["2024-02"] == pytest.approx(-5.0)
    # Parent's filter values enumerate every exact category in the subtree
    assert parent.categories == ["groceries", "groceries-ah", "groceries-jumbo"]

    assert _child(parent, "groceries-ah").total == pytest.approx(-10.0)
    assert _child(parent, "groceries-jumbo").total == pytest.approx(-20.0)
    # The parent's own (exact) transactions get their own sub-row
    assert _child(parent, "groceries").total == pytest.approx(-5.0)

    # A category without children stays a flat row
    salary = _row(table, "salary")
    assert not salary.has_children
    assert salary.categories == ["salary"]


def test_single_child_still_grouped_under_parent(db):
    _seed(db, [_mk(id="a", category="auto-fuel", amount=-60.0)])
    table = aggregate(db, _params())
    parent = _row(table, "auto")
    assert parent.has_children
    assert _child(parent, "auto-fuel").total == pytest.approx(-60.0)


def test_row_column_and_grand_totals(db):
    _seed(db, [
        _mk(id="a", category="dining", amount=-10.0, transactiondate=date(2024, 1, 5)),
        _mk(id="b", category="salary", amount=100.0, transactiondate=date(2024, 1, 25)),
        _mk(id="c", category="dining", amount=-30.0, transactiondate=date(2024, 2, 5)),
    ])
    table = aggregate(db, _params(date_to=date(2024, 2, 29)))
    assert table.column_totals["2024-01"] == pytest.approx(90.0)
    assert table.column_totals["2024-02"] == pytest.approx(-30.0)
    assert table.grand_total == pytest.approx(60.0)
    assert _row(table, "dining").total == pytest.approx(-40.0)


def test_empty_cells_absent(db):
    _seed(db, [_mk(id="a", category="dining", amount=-10.0,
                   transactiondate=date(2024, 1, 5))])
    table = aggregate(db, _params(date_to=date(2024, 3, 31)))
    row = _row(table, "dining")
    assert "2024-02" not in row.cells
    assert "2024-03" not in row.cells


def test_window_excludes_outside_dates(db):
    _seed(db, [
        _mk(id="a", category="dining", amount=-10.0, transactiondate=date(2023, 12, 31)),
        _mk(id="b", category="dining", amount=-20.0, transactiondate=date(2024, 1, 1)),
        _mk(id="c", category="dining", amount=-40.0, transactiondate=date(2025, 1, 1)),
    ])
    table = aggregate(db, _params())
    assert _row(table, "dining").total == pytest.approx(-20.0)


def test_year_granularity(db):
    _seed(db, [
        _mk(id="a", category="dining", amount=-10.0, transactiondate=date(2024, 3, 1)),
        _mk(id="b", category="dining", amount=-20.0, transactiondate=date(2025, 3, 1)),
    ])
    table = aggregate(db, _params(granularity="year", date_to=date(2025, 12, 31)))
    row = _row(table, "dining")
    assert row.cells["2024"] == pytest.approx(-10.0)
    assert row.cells["2025"] == pytest.approx(-20.0)


def test_account_filter(db):
    _seed(db, [
        _mk(id="a", accountNumber="NL01", category="dining", amount=-10.0),
        _mk(id="b", accountNumber="NL02", category="dining", amount=-20.0),
    ])
    table = aggregate(db, _params(accounts=["NL01"]))
    assert _row(table, "dining").total == pytest.approx(-10.0)


def test_categories_lowercased(db):
    _seed(db, [
        _mk(id="a", category="Dining", amount=-1.0),
        _mk(id="b", category="dining", amount=-2.0),
    ])
    table = aggregate(db, _params())
    assert _row(table, "dining").total == pytest.approx(-3.0)


# ---------------------------------------------------------------------------
# Params round-trip + link building
# ---------------------------------------------------------------------------


def test_params_from_query_string_defaults():
    p = TrendsParams.from_query_string("")
    assert p.granularity == "month"
    assert p.date_from is None and p.date_to is None
    assert p.accounts == []


def test_params_round_trip():
    p = TrendsParams(
        granularity="year",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 12, 31),
        accounts=["NL01", "NL02"],
    )
    qs = p.to_query_string()
    assert TrendsParams.from_query_string(qs) == p


def test_params_invalid_granularity_falls_back():
    p = TrendsParams.from_query_string("granularity=day")
    assert p.granularity == "month"


def test_transactions_link_uses_filter_param_names():
    url = transactions_link(
        ["groceries-ah"], date(2024, 1, 1), date(2024, 1, 31), []
    )
    assert url == "/transactions?date_from=2024-01-01&date_to=2024-01-31&category=groceries-ah"


def test_transactions_link_multiple_categories_and_account():
    url = transactions_link(
        ["groceries", "groceries-ah"], date(2024, 1, 1), date(2024, 12, 31), ["NL01"]
    )
    assert url == (
        "/transactions?date_from=2024-01-01&date_to=2024-12-31"
        "&category=groceries&category=groceries-ah&account=NL01"
    )


def test_transactions_link_round_trips_through_filter():
    from abn_combined.core.filters import TransactionFilter

    url = transactions_link(["dining"], date(2024, 2, 1), date(2024, 2, 29), ["NL01"])
    f = TransactionFilter.from_query_string(url.split("?", 1)[1])
    assert f.categories == ["dining"]
    assert f.date_from == date(2024, 2, 1)
    assert f.date_to == date(2024, 2, 29)
    assert f.accounts == ["NL01"]
