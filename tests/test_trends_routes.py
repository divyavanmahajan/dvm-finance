"""Route + integration tests for GET /trends (category trends view)."""

from __future__ import annotations

from datetime import date

import pytest

from abn_combined.core.filters import TransactionFilter, build_query
from abn_combined.core.models import Transaction
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
def seed(app):
    factory = get_session_factory()
    db = factory()
    txns = [
        _mk(id="g1", category="groceries-ah", amount=-25.5,
            transactiondate=date(2024, 1, 5)),
        _mk(id="g2", category="groceries-ah", amount=-14.5,
            transactiondate=date(2024, 1, 20)),
        _mk(id="g3", category="groceries-jumbo", amount=-30.0,
            transactiondate=date(2024, 2, 10)),
        _mk(id="d1", category="dining", amount=-50.0, transactiondate=date(2024, 2, 14)),
        _mk(id="u1", category=None, amount=-8.0, transactiondate=date(2024, 1, 9)),
        _mk(id="s1", category="salary", amount=1500.0, transactiondate=date(2024, 1, 25),
            accountNumber="NL02"),
    ]
    for t in txns:
        db.add(t)
    db.commit()
    db.close()
    return factory


QS = "date_from=2024-01-01&date_to=2024-02-29"


def test_trends_page_renders(client, seed):
    r = client.get(f"/trends?{QS}")
    assert r.status_code == 200
    assert "Trends" in r.text
    assert "groceries" in r.text
    assert "Uncategorized" in r.text


def test_trends_replaces_placeholder(client, seed):
    r = client.get("/trends")
    assert r.status_code == 200
    assert "Category Trends" in r.text
    assert "coming in a later step" not in r.text.lower()


def test_trends_table_partial(client, seed):
    r = client.get(f"/trends/table?{QS}")
    assert r.status_code == 200
    assert "<html" not in r.text.lower()
    assert "groceries" in r.text


def test_cell_click_through_url_exact(client, seed):
    r = client.get(f"/trends?{QS}")
    # Leaf cell: groceries-ah × Jan 2024
    expected = (
        "/transactions?date_from=2024-01-01&amp;date_to=2024-01-31"
        "&amp;category=groceries-ah"
    )
    assert expected in r.text


def test_parent_cell_click_through_enumerates_children(client, seed):
    r = client.get(f"/trends?{QS}")
    # Parent subtotal cell: groceries × Feb 2024 lists every exact category
    expected = (
        "/transactions?date_from=2024-02-01&amp;date_to=2024-02-29"
        "&amp;category=groceries-ah&amp;category=groceries-jumbo"
    )
    assert expected in r.text


def test_row_label_links_to_full_window(client, seed):
    r = client.get(f"/trends?{QS}")
    expected = (
        "/transactions?date_from=2024-01-01&amp;date_to=2024-02-29"
        "&amp;category=dining"
    )
    assert expected in r.text


def test_uncategorized_click_through(client, seed):
    r = client.get(f"/trends?{QS}")
    expected = (
        "/transactions?date_from=2024-01-01&amp;date_to=2024-01-31"
        "&amp;category=uncategorized"
    )
    assert expected in r.text


def test_account_filter_propagates_to_links(client, seed):
    r = client.get(f"/trends?{QS}&account=NL02")
    assert "salary" in r.text
    assert "groceries" not in r.text
    expected = (
        "/transactions?date_from=2024-01-01&amp;date_to=2024-01-31"
        "&amp;category=salary&amp;account=NL02"
    )
    assert expected in r.text


def test_year_granularity_control(client, seed):
    r = client.get(f"/trends?{QS}&granularity=year")
    assert r.status_code == 200
    expected = (
        "/transactions?date_from=2024-01-01&amp;date_to=2024-02-29"
        "&amp;category=dining"
    )
    assert expected in r.text


def test_negative_amounts_styled(client, seed):
    r = client.get(f"/trends?{QS}")
    assert 'class="num neg"' in r.text


# ---------------------------------------------------------------------------
# Sortable column headers
# ---------------------------------------------------------------------------


def test_headers_are_sortable_links(client, seed):
    r = client.get(f"/trends/table?{QS}")
    assert "sortable-th" in r.text
    assert "sort=total_asc" in r.text  # default sort is category_asc; total starts asc


def test_sort_by_total_asc_orders_rows(client, seed):
    r = client.get(f"/trends/table?{QS}&sort=total_asc")
    body = r.text
    # totals in this window: groceries ~-70, dining -50, uncategorized -8.
    # total_asc (most negative first) => groceries, dining, uncategorized.
    assert body.index("groceries") < body.index("dining") < body.index("Uncategorized")


def test_sort_category_desc_orders_alphabetically_reversed(client, seed):
    r = client.get(f"/trends/table?{QS}&sort=category_desc")
    body = r.text
    assert body.index("Uncategorized") < body.index("groceries")


def test_sort_toggle_asc_desc_on_repeated_click(client, seed):
    r_asc = client.get(f"/trends/table?{QS}&sort=total_asc")
    assert "sort=total_desc" in r_asc.text
    r_desc = client.get(f"/trends/table?{QS}&sort=total_desc")
    assert "sort=total_asc" in r_desc.text


# ---------------------------------------------------------------------------
# Integration: a cell's linked transactions sum to the cell value
# ---------------------------------------------------------------------------


def test_cell_link_transactions_sum_to_cell_value(client, seed):
    from abn_combined.core.trends import TrendsParams, aggregate, transactions_link

    factory = seed
    db = factory()
    try:
        params = TrendsParams(date_from=date(2024, 1, 1), date_to=date(2024, 2, 29))
        table = aggregate(db, params)

        rows = list(table.rows)
        for parent in table.rows:
            rows.extend(parent.children)

        checked = 0
        for row in rows:
            for period in table.periods:
                if period.key not in row.cells:
                    continue
                url = transactions_link(
                    row.categories, period.start, period.end, params.accounts
                )
                f = TransactionFilter.from_query_string(url.split("?", 1)[1])
                txns = build_query(db, f).all()
                linked_sum = float(sum(t.amount for t in txns))
                assert linked_sum == pytest.approx(row.cells[period.key]), (
                    f"cell {row.label} × {period.key}: link {url} sums to "
                    f"{linked_sum}, cell shows {row.cells[period.key]}"
                )
                checked += 1
        assert checked >= 6  # every seeded category/period combination exercised
    finally:
        db.close()


def test_row_label_link_transactions_sum_to_row_total(client, seed):
    from abn_combined.core.trends import TrendsParams, aggregate, transactions_link

    factory = seed
    db = factory()
    try:
        params = TrendsParams(date_from=date(2024, 1, 1), date_to=date(2024, 2, 29))
        table = aggregate(db, params)
        lo, hi = params.effective_window()
        for row in table.rows:
            url = transactions_link(row.categories, lo, hi, params.accounts)
            f = TransactionFilter.from_query_string(url.split("?", 1)[1])
            txns = build_query(db, f).all()
            assert float(sum(t.amount for t in txns)) == pytest.approx(row.total)
    finally:
        db.close()
