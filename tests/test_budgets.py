"""Tests for budget-vs-actual computation and the /budgets route.

TDD: written before implementation. Core logic tested in isolation, then route.
"""

from __future__ import annotations

from datetime import date

import pytest

from abn_combined.core.models import Budget, Transaction
from abn_combined.db import get_session_factory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _txn(id_, amount, category=None, manual_category=None, txdate=None):
    return Transaction(
        id=id_,
        accountNumber="NL01",
        transactiondate=txdate or date(2024, 1, 15),
        amount=amount,
        currency="EUR",
        description="test",
        category=category,
        manual_category=manual_category,
    )


# ---------------------------------------------------------------------------
# core/budget_report.py unit tests
# ---------------------------------------------------------------------------


class TestGetPeriodDates:
    def test_month_period(self):
        from abn_combined.core.budget_report import get_period_dates

        start, end = get_period_dates("month", date(2024, 3, 15))
        assert start == date(2024, 3, 1)
        assert end == date(2024, 3, 31)

    def test_year_period(self):
        from abn_combined.core.budget_report import get_period_dates

        start, end = get_period_dates("year", date(2024, 6, 1))
        assert start == date(2024, 1, 1)
        assert end == date(2024, 12, 31)

    def test_week_period_monday(self):
        from abn_combined.core.budget_report import get_period_dates

        # 2024-01-15 is a Monday
        start, end = get_period_dates("week", date(2024, 1, 15))
        assert start == date(2024, 1, 15)
        assert end == date(2024, 1, 21)

    def test_week_period_wednesday(self):
        from abn_combined.core.budget_report import get_period_dates

        # 2024-01-17 is a Wednesday
        start, end = get_period_dates("week", date(2024, 1, 17))
        assert start == date(2024, 1, 15)
        assert end == date(2024, 1, 21)

    def test_month_february(self):
        from abn_combined.core.budget_report import get_period_dates

        start, end = get_period_dates("month", date(2024, 2, 10))
        assert start == date(2024, 2, 1)
        assert end == date(2024, 2, 29)  # 2024 is a leap year

    def test_invalid_period_raises(self):
        from abn_combined.core.budget_report import get_period_dates

        with pytest.raises(ValueError):
            get_period_dates("decade", date(2024, 1, 1))


class TestComputeActual:
    """Test compute_actual against a hand-computed fixture."""

    @pytest.fixture
    def seeded_db(self, app):
        factory = get_session_factory()
        db = factory()
        # January 2024: food spending = 25 + 50 = 75, income = +1500
        db.add(_txn("a1", -25.0, category="food", txdate=date(2024, 1, 5)))
        db.add(_txn("a2", -50.0, category="food-restaurants", txdate=date(2024, 1, 10)))
        db.add(_txn("a3", 1500.0, category="income", txdate=date(2024, 1, 20)))
        # Manual override: this one has food as manual, not rule-assigned
        db.add(
            _txn(
                "a4",
                -30.0,
                category="housing",
                manual_category="food",
                txdate=date(2024, 1, 25),
            )
        )
        # Outside January — should not be counted
        db.add(_txn("a5", -20.0, category="food", txdate=date(2024, 2, 5)))
        db.commit()
        db.close()
        return factory

    def test_actual_month_food_includes_manual(self, seeded_db):
        """Hand-computed: food actuals for Jan 2024 = 25 + 50 + 30 = 105."""
        from abn_combined.core.budget_report import compute_actual

        factory = seeded_db
        db = factory()
        actual = compute_actual(
            db, "food", date(2024, 1, 1), date(2024, 1, 31)
        )
        db.close()
        # abs(−25) + abs(−50) + abs(−30) = 105
        # a3 (income) and a5 (feb) excluded
        assert actual == pytest.approx(105.0, abs=0.01)

    def test_actual_month_food_excludes_other_month(self, seeded_db):
        """Transactions in Feb should not count for Jan period."""
        from abn_combined.core.budget_report import compute_actual

        factory = seeded_db
        db = factory()
        actual = compute_actual(
            db, "food", date(2024, 2, 1), date(2024, 2, 29)
        )
        db.close()
        # Only a5: abs(−20) = 20
        assert actual == pytest.approx(20.0, abs=0.01)

    def test_actual_hierarchical_child_included(self, seeded_db):
        """food:restaurants is a child of food; should be counted."""
        from abn_combined.core.budget_report import compute_actual

        factory = seeded_db
        db = factory()
        actual = compute_actual(
            db, "food", date(2024, 1, 1), date(2024, 1, 31)
        )
        db.close()
        # a1 + a2 + a4 = 25+50+30 = 105
        assert actual == pytest.approx(105.0, abs=0.01)

    def test_actual_income_not_included_as_spending(self, seeded_db):
        """Income (positive amounts) should not inflate spending total."""
        from abn_combined.core.budget_report import compute_actual

        factory = seeded_db
        db = factory()
        actual = compute_actual(
            db, "income", date(2024, 1, 1), date(2024, 1, 31)
        )
        db.close()
        # a3: abs(1500) = 1500
        assert actual == pytest.approx(1500.0, abs=0.01)


class TestAverageMonthlySpend:
    """`average_monthly_spend` proposes an amount for the bulk-create button
    and the manual "Add budget" form's hint — average abs(amount) over the
    last N *full* months before `reference_date`'s month (current
    in-progress month excluded so a partial month never drags it down)."""

    @pytest.fixture
    def seeded(self, app):
        factory = get_session_factory()
        db = factory()
        # reference_date = 2024-04-15: last 3 full months are Jan, Feb, Mar.
        db.add(_txn("m1", -100.0, category="food", txdate=date(2024, 1, 10)))
        db.add(_txn("m2", -200.0, category="food-restaurants", txdate=date(2024, 2, 10)))
        db.add(_txn("m3", -300.0, category="food", txdate=date(2024, 3, 10)))
        db.add(_txn("m4", -9999.0, category="food", txdate=date(2024, 4, 10)))  # current month, excluded
        db.commit()
        db.close()
        return factory

    def test_average_over_last_three_full_months(self, seeded):
        from abn_combined.core.budget_report import average_monthly_spend

        db = seeded()
        avg = average_monthly_spend(db, "food", reference_date=date(2024, 4, 15))
        db.close()
        # (100 + 200 + 300) / 3 = 200 — includes the "food-restaurants" child
        # (hierarchical match) and excludes the April (current month) row.
        assert avg == pytest.approx(200.0, abs=0.01)

    def test_no_recent_spend_is_zero(self, app):
        from abn_combined.core.budget_report import average_monthly_spend

        factory = get_session_factory()
        db = factory()
        avg = average_monthly_spend(db, "nonexistent", reference_date=date(2024, 4, 15))
        db.close()
        assert avg == 0.0


class TestDistinctTopLevelCategories:
    def test_groups_by_first_hyphen_segment(self, app):
        from abn_combined.core.budget_report import distinct_top_level_categories

        factory = get_session_factory()
        db = factory()
        db.add(_txn("t1", -10.0, category="food-groceries"))
        db.add(_txn("t2", -10.0, category="food-restaurants", txdate=date(2024, 2, 1)))
        db.add(_txn("t3", -10.0, category="housing", txdate=date(2024, 3, 1)))
        db.add(_txn("t4", 1000.0, manual_category="income-salary", txdate=date(2024, 4, 1)))
        db.commit()
        tops = distinct_top_level_categories(db)
        db.close()
        assert tops == ["food", "housing", "income"]


class TestBudgetVsActualTable:
    @pytest.fixture
    def seeded(self, app):
        factory = get_session_factory()
        db = factory()
        db.add(Budget(id=1, category="food", amount=100.0, period="month"))
        db.add(Budget(id=2, category="housing", amount=500.0, period="month"))
        # Validity: budget 1 active always; budget 2 has end_date before current period
        db.add(
            _txn("b1", -75.0, category="food", txdate=date(2024, 1, 10))
        )
        db.add(
            _txn("b2", -600.0, category="housing", txdate=date(2024, 1, 15))
        )
        db.commit()
        db.close()
        return factory

    def test_budget_vs_actual_rows(self, seeded):
        from abn_combined.core.budget_report import budget_vs_actual_table

        factory = seeded
        db = factory()
        rows = budget_vs_actual_table(db, reference_date=date(2024, 1, 20))
        db.close()
        by_cat = {r["category"]: r for r in rows}
        assert "food" in by_cat
        food = by_cat["food"]
        assert food["budget"] == pytest.approx(100.0, abs=0.01)
        assert food["actual"] == pytest.approx(75.0, abs=0.01)
        assert food["remaining"] == pytest.approx(25.0, abs=0.01)
        assert food["status"] == "under"

    def test_over_budget_status(self, seeded):
        from abn_combined.core.budget_report import budget_vs_actual_table

        factory = seeded
        db = factory()
        rows = budget_vs_actual_table(db, reference_date=date(2024, 1, 20))
        db.close()
        by_cat = {r["category"]: r for r in rows}
        housing = by_cat["housing"]
        assert housing["status"] == "over"
        assert housing["actual"] == pytest.approx(600.0, abs=0.01)

    def test_validity_dates_filter_expired_budget(self, app):
        """Budget with end_date before period_start should be excluded."""
        from abn_combined.core.budget_report import budget_vs_actual_table

        factory = get_session_factory()
        db = factory()
        db.add(
            Budget(
                id=10,
                category="expired",
                amount=100.0,
                period="month",
                end_date=date(2023, 12, 31),  # expired
            )
        )
        db.commit()
        rows = budget_vs_actual_table(db, reference_date=date(2024, 1, 15))
        db.close()
        assert all(r["category"] != "expired" for r in rows)

    def test_validity_dates_filter_future_budget(self, app):
        """Budget with start_date after period_end should be excluded."""
        from abn_combined.core.budget_report import budget_vs_actual_table

        factory = get_session_factory()
        db = factory()
        db.add(
            Budget(
                id=11,
                category="future",
                amount=100.0,
                period="month",
                start_date=date(2024, 3, 1),  # future relative to Jan 2024
            )
        )
        db.commit()
        rows = budget_vs_actual_table(db, reference_date=date(2024, 1, 15))
        db.close()
        assert all(r["category"] != "future" for r in rows)


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


def test_budgets_page_renders(client):
    r = client.get("/budgets")
    assert r.status_code == 200
    assert "Budgets" in r.text


def test_budgets_page_shows_table(client, app):
    factory = get_session_factory()
    db = factory()
    db.add(Budget(id=99, category="test-cat", amount=250.0, period="month"))
    db.commit()
    db.close()

    r = client.get("/budgets")
    assert r.status_code == 200
    assert "test-cat" in r.text


def test_budget_create(client):
    r = client.post(
        "/budgets/create",
        data={"category": "food", "amount": "200", "period": "month"},
    )
    assert r.status_code in (200, 302, 303)


def test_budget_create_duplicate_returns_error(client):
    client.post(
        "/budgets/create",
        data={"category": "food", "amount": "200", "period": "month"},
    )
    r = client.post(
        "/budgets/create",
        data={"category": "food", "amount": "300", "period": "month"},
    )
    # Should show error or redirect — not 500
    assert r.status_code < 500


def test_budget_delete(client, app):
    factory = get_session_factory()
    db = factory()
    db.add(Budget(id=50, category="deleteme", amount=100.0, period="month"))
    db.commit()
    db.close()

    r = client.post("/budgets/50/delete")
    assert r.status_code in (200, 302, 303)

    db2 = factory()
    assert db2.get(Budget, 50) is None
    db2.close()


def test_budget_edit_renders_form(client, app):
    factory = get_session_factory()
    db = factory()
    db.add(Budget(id=51, category="editme", amount=150.0, period="month"))
    db.commit()
    db.close()

    r = client.get("/budgets/51/edit")
    assert r.status_code == 200
    assert "editme" in r.text


def test_budget_update(client, app):
    factory = get_session_factory()
    db = factory()
    db.add(Budget(id=52, category="updateme", amount=100.0, period="month"))
    db.commit()
    db.close()

    r = client.post(
        "/budgets/52/update",
        data={"category": "updateme", "amount": "300", "period": "month"},
    )
    assert r.status_code in (200, 302, 303)

    db2 = factory()
    b = db2.get(Budget, 52)
    assert float(b.amount) == pytest.approx(300.0, abs=0.01)
    db2.close()


# ---------------------------------------------------------------------------
# New: average hint + bulk-create-for-top-level-categories
# ---------------------------------------------------------------------------




def test_average_hint_route_shows_recent_average(client, app):
    factory = get_session_factory()
    db = factory()
    ref = date.today().replace(day=15)
    prev_year, prev_month = (ref.year, ref.month - 1) if ref.month > 1 else (ref.year - 1, 12)
    db.add(_txn("h1", -60.0, category="hint-cat", txdate=date(prev_year, prev_month, 5)))
    db.commit()
    db.close()

    r = client.get("/budgets/average-hint", params={"category": "hint-cat"})
    assert r.status_code == 200
    assert "Recent average" in r.text


def test_average_hint_route_empty_category_returns_blank(client) -> None:
    r = client.get("/budgets/average-hint", params={"category": ""})
    assert r.status_code == 200
    assert r.text.strip() == ""


def test_average_hint_route_no_recent_spend(client) -> None:
    r = client.get("/budgets/average-hint", params={"category": "never-seen-category"})
    assert r.status_code == 200
    assert "No recent spend" in r.text








def test_budgets_page_defaults_to_month_tab(client):
    """With no ``period`` query param the page opens on the Monthly tab —
    the tab link is marked active and the yearly one is not."""
    import re

    r = client.get("/budgets")
    assert r.status_code == 200
    assert 'href="/budgets?period=month' in r.text
    assert 'href="/budgets?period=year' in r.text
    # The Monthly tab link carries the active class; the Yearly one does not.
    monthly = re.search(r'class="nav-link([^"]*)"\s+href="/budgets\?period=month', r.text)
    yearly = re.search(r'class="nav-link([^"]*)"\s+href="/budgets\?period=year', r.text)
    assert monthly and "active" in monthly.group(1)
    assert yearly and "active" not in yearly.group(1)






# ---------------------------------------------------------------------------
# Several budgets for one category (repeating-budgets-with-override)
# ---------------------------------------------------------------------------


class TestValidityRules:
    @pytest.fixture
    def db(self, app):
        factory = get_session_factory()
        session = factory()
        session.add(Budget(id=70, category="food", amount=100, period="month",
                           start_date=date(2026, 7, 1), end_date=date(2026, 10, 31)))
        session.add(Budget(id=71, category="fun", amount=50, period="month"))
        session.add(Budget(id=72, category="food", amount=900, period="year"))
        session.commit()
        yield session
        session.close()

    def test_bounds_accept_period_edges(self):
        from abn_combined.core.budget_report import check_validity_bounds

        assert check_validity_bounds("month", date(2026, 11, 1), None) is None
        assert check_validity_bounds("month", None, date(2026, 2, 28)) is None
        assert check_validity_bounds("year", date(2026, 1, 1), date(2026, 12, 31)) is None
        assert check_validity_bounds("month", None, None) is None

    def test_bounds_reject_a_start_in_the_middle_of_a_month(self):
        from abn_combined.core.budget_report import check_validity_bounds

        assert "first day of a month" in check_validity_bounds("month", date(2026, 11, 15), None)
        assert "last day of a month" in check_validity_bounds("month", None, date(2026, 11, 15))
        assert "first day of a year" in check_validity_bounds("year", date(2026, 2, 1), None)

    def test_bounds_reject_an_end_before_the_start(self):
        from abn_combined.core.budget_report import check_validity_bounds

        assert check_validity_bounds("month", date(2026, 11, 1), date(2026, 10, 31))

    def test_touching_ranges_do_not_overlap(self, db):
        from abn_combined.core.budget_report import find_overlap

        assert find_overlap(db, "food", "month", date(2026, 11, 1), None) is None
        assert find_overlap(db, "food", "month", None, date(2026, 6, 30)) is None

    def test_open_ranges_overlap(self, db):
        from abn_combined.core.budget_report import find_overlap

        assert find_overlap(db, "food", "month", None, None).id == 70
        assert find_overlap(db, "food", "month", date(2026, 10, 1), None).id == 70
        assert find_overlap(db, "food", "month", None, date(2026, 7, 31)).id == 70
        # An open budget overlaps each range.
        assert find_overlap(db, "fun", "month", date(2030, 1, 1), date(2030, 1, 31)).id == 71

    def test_other_period_and_budget_under_edit_do_not_count(self, db):
        from abn_combined.core.budget_report import find_overlap

        assert find_overlap(db, "food", "month", date(2026, 8, 1), None, exclude_id=70) is None
        assert find_overlap(db, "food", "year", date(2026, 1, 1), None).id == 72


def _add(*budgets):
    factory = get_session_factory()
    db = factory()
    db.add_all(budgets)
    db.commit()
    db.close()


def _budgets(category, period="month"):
    factory = get_session_factory()
    db = factory()
    rows = (db.query(Budget).filter(Budget.category == category, Budget.period == period)
            .order_by(Budget.start_date).all())
    out = [(r.start_date, r.end_date, float(r.amount)) for r in rows]
    db.close()
    return out


def _last_full_month():
    today = date.today()
    return (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)


# --- 2.1 create and update with the overlap rule ----------------------------

def test_create_after_an_ended_budget_stores(client, app):
    _add(Budget(category="food", amount=100, period="month",
                start_date=date(2026, 7, 1), end_date=date(2026, 10, 31)))
    r = client.post("/budgets/create", data={
        "category": "food", "amount": "150", "period": "month", "start_date": "2026-11-01"},
        follow_redirects=False)
    assert r.status_code == 303
    assert _budgets("food") == [(date(2026, 7, 1), date(2026, 10, 31), 100.0),
                                (date(2026, 11, 1), None, 150.0)]


def test_create_overlap_names_the_other_budget(client, app):
    _add(Budget(category="food", amount=100, period="month", start_date=date(2026, 7, 1)))
    r = client.post("/budgets/create", data={
        "category": "food", "amount": "150", "period": "month", "start_date": "2026-11-01"})
    assert r.status_code == 200
    assert "overlaps the month budget for &#39;food&#39; (2026-07-01 to no end)" in r.text
    assert len(_budgets("food")) == 1


def test_update_onto_an_overlap_returns_400(client, app):
    _add(Budget(id=80, category="food", amount=100, period="month",
                start_date=date(2026, 7, 1), end_date=date(2026, 10, 31)),
         Budget(id=81, category="food", amount=150, period="month", start_date=date(2026, 11, 1)))
    r = client.post("/budgets/80/update", data={
        "category": "food", "amount": "100", "period": "month",
        "start_date": "2026-07-01", "end_date": ""})
    assert r.status_code == 400


def test_create_with_a_start_in_the_middle_of_a_month_returns_400(client):
    r = client.post("/budgets/create", data={
        "category": "food", "amount": "150", "period": "month", "start_date": "2026-11-15"})
    assert r.status_code == 400
    assert "first day of a month" in r.text


# --- 2.2 the add form repeats by default ------------------------------------

def test_add_form_has_a_start_and_no_end(client):
    from abn_combined.core.budget_report import get_period_dates

    start, _ = get_period_dates("month", date.today())
    r = client.get("/budgets")
    assert f'id="add-start-date" name="start_date" value="{start.isoformat()}"' in r.text
    assert 'id="add-end-date" name="end_date" value=""' in r.text


# --- 3.1 month and year selector --------------------------------------------

def test_selector_defaults_to_the_current_month_and_year(client):
    today = date.today()
    r = client.get("/budgets")
    assert f'name="month"\n               value="{today:%Y-%m}"' in r.text
    r = client.get("/budgets?period=year")
    assert f'<option value="{today.year}" selected>' in r.text


def test_selected_month_and_year_report_their_window(client, app):
    _add(Budget(category="food", amount=100, period="month",
                start_date=date(2026, 7, 1), end_date=date(2026, 10, 31)),
         Budget(category="food", amount=1200, period="year",
                start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)))
    r = client.get("/budgets?period=month&month=2026-08")
    assert "2026-08-01 → 2026-08-31" in r.text
    assert "food" in r.text
    assert "food" not in client.get("/budgets?period=month&month=2026-11").text.split("<tbody>")[-1]
    r = client.get("/budgets?period=year&year=2025")
    assert "2025-01-01 → 2025-12-31" in r.text


def test_malformed_month_returns_400(client):
    assert client.get("/budgets?period=month&month=2026-8").status_code == 400
    assert client.get("/budgets?period=month&month=2026-13").status_code == 400
    assert client.get("/budgets?period=year&year=26").status_code == 400


def test_old_ref_link_selects_its_month(client):
    r = client.get("/budgets?period=month&ref=2026-08-15")
    assert 'value="2026-08"' in r.text
    assert "2026-08-01 → 2026-08-31" in r.text or "No monthly budgets" in r.text


def test_create_link_in_each_tab_carries_the_selection(client):
    r = client.get("/budgets?period=month&month=2027-03")
    assert 'href="/budgets/seed?period=month&amp;start=2027-03"' in r.text
    r = client.get("/budgets?period=year&year=2027")
    assert 'href="/budgets/seed?period=year&amp;start=2027"' in r.text


def test_tab_links_keep_the_selection(client):
    r = client.get("/budgets?period=month&month=2027-03")
    assert 'href="/budgets?period=year&amp;year=2027"' in r.text
    r = client.get("/budgets?period=year&year=2025")
    assert 'href="/budgets?period=month&amp;month=2025-01"' in r.text


# --- 3.2 sortable table ------------------------------------------------------

@pytest.fixture
def three_budgets(app):
    _add(Budget(category="aaa", amount=50, period="month"),
         Budget(category="bbb", amount=300, period="month"),
         Budget(category="ccc", amount=120, period="month"))
    # Spend in the selected month: ccc over, aaa near, bbb under.
    factory = get_session_factory()
    db = factory()
    db.add(_txn("s1", -45.0, category="aaa", txdate=date(2026, 8, 3)))
    db.add(_txn("s2", -10.0, category="bbb", txdate=date(2026, 8, 3)))
    db.add(_txn("s3", -200.0, category="ccc", txdate=date(2026, 8, 3)))
    db.commit()
    db.close()


def _order(client, query):
    import re

    body = client.get("/budgets?period=month&month=2026-08" + query).text.split("<tbody>")[1]
    return re.findall(r'<td><a href="[^"]*">(\w+)</a></td>', body)


def test_default_sort_is_the_largest_budget_first(client, three_budgets):
    assert _order(client, "") == ["bbb", "ccc", "aaa"]


def test_each_column_sorts_both_ways(client, three_budgets):
    assert _order(client, "&sort=actual_asc") == ["bbb", "aaa", "ccc"]
    assert _order(client, "&sort=actual_desc") == ["ccc", "aaa", "bbb"]
    assert _order(client, "&sort=category_desc") == ["ccc", "bbb", "aaa"]
    assert _order(client, "&sort=remaining_asc") == ["ccc", "aaa", "bbb"]
    assert _order(client, "&sort=used_desc") == ["ccc", "aaa", "bbb"]
    for column in ("period", "window"):
        # Equal values keep the category order.
        assert _order(client, f"&sort={column}_asc") == ["aaa", "bbb", "ccc"]


def test_status_sorts_over_near_under(client, three_budgets):
    assert _order(client, "&sort=status_asc") == ["ccc", "aaa", "bbb"]


def test_header_click_sorts_then_reverses(client, three_budgets):
    r = client.get("/budgets?period=month&month=2026-08")
    assert 'href="/budgets?period=month&amp;month=2026-08&amp;sort=actual_asc"' in r.text
    r = client.get("/budgets?period=month&month=2026-08&sort=actual_asc")
    assert 'href="/budgets?period=month&amp;month=2026-08&amp;sort=actual_desc"' in r.text


def test_unknown_sort_falls_back_to_the_default(client, three_budgets):
    assert _order(client, "&sort=nonsense") == ["bbb", "ccc", "aaa"]


# --- 4.1 seed_budgets --------------------------------------------------------

class TestSeedBudgets:
    def _seed(self, choices, period="month", start=date(2026, 11, 1)):
        from abn_combined.core.budget_report import seed_budgets

        factory = get_session_factory()
        db = factory()
        result = seed_budgets(db, period, start, choices, "seeded")
        db.close()
        return result

    def test_new_budget_has_no_end(self, app):
        assert self._seed([("food", 80.0)])["created"] == ["food"]
        assert _budgets("food") == [(date(2026, 11, 1), None, 80.0)]

    def test_override_ends_the_old_budget_on_the_day_before(self, app):
        _add(Budget(category="food", amount=400, period="month", start_date=date(2026, 7, 1)))
        result = self._seed([("food", 450.0)])
        assert (result["ended"], result["created"]) == (["food"], ["food"])
        assert _budgets("food") == [(date(2026, 7, 1), date(2026, 10, 31), 400.0),
                                    (date(2026, 11, 1), None, 450.0)]

    def test_override_of_a_budget_without_a_start(self, app):
        _add(Budget(category="food", amount=400, period="month"))
        self._seed([("food", 450.0)])
        assert _budgets("food") == [(None, date(2026, 10, 31), 400.0),
                                    (date(2026, 11, 1), None, 450.0)]

    def test_override_in_the_start_month_changes_the_amount(self, app):
        _add(Budget(category="food", amount=400, period="month", start_date=date(2026, 11, 1)))
        assert self._seed([("food", 450.0)])["changed"] == ["food"]
        assert _budgets("food") == [(date(2026, 11, 1), None, 450.0)]

    def test_a_later_budget_limits_the_new_end(self, app):
        _add(Budget(category="food", amount=500, period="month", start_date=date(2027, 3, 1)))
        self._seed([("food", 450.0)])
        assert _budgets("food") == [(date(2026, 11, 1), date(2027, 2, 28), 450.0),
                                    (date(2027, 3, 1), None, 500.0)]

    def test_expired_budget_stays_as_history(self, app):
        _add(Budget(category="food", amount=400, period="month",
                    start_date=date(2026, 7, 1), end_date=date(2026, 7, 31)))
        result = self._seed([("food", 450.0)])
        assert result["ended"] == []
        assert _budgets("food") == [(date(2026, 7, 1), date(2026, 7, 31), 400.0),
                                    (date(2026, 11, 1), None, 450.0)]

    def test_yearly_start_snaps_to_the_first_day_of_the_year(self, app):
        self._seed([("food", 1200.0)], period="year", start=date(2027, 6, 1))
        assert _budgets("food", "year") == [(date(2027, 1, 1), None, 1200.0)]

    def test_income_and_transfer_never_get_a_budget(self, app):
        self._seed([("income", 5000.0), ("transfer", 10.0), ("food", 80.0)])
        assert _budgets("income") == [] and _budgets("transfer") == []


# --- 4.2 the dialog ----------------------------------------------------------

@pytest.fixture
def recent_spend(app):
    year, month = _last_full_month()
    factory = get_session_factory()
    db = factory()
    db.add(_txn("r1", -90.0, category="food-shop", txdate=date(year, month, 5)))
    db.add(_txn("r2", -30.0, category="fun", txdate=date(year, month, 6)))
    db.add(_txn("r3", 3000.0, category="income-pay", txdate=date(year, month, 7)))
    db.add(_txn("r4", -50.0, category="transfer-own", txdate=date(year, month, 8)))
    db.add(_txn("r5", -80.0, category="stale", txdate=date(2020, 1, 5)))
    db.commit()
    db.close()


def _seed_rows(html):
    import re

    return re.findall(r'<tr data-category="([^"]+)">.*?(checked)?\s+aria-label', html, re.S)


def test_dialog_defaults_to_the_start_of_the_tab(client, recent_spend):
    r = client.get("/budgets/seed?period=month&start=2027-03")
    assert 'id="seed-start" name="start"\n             value="2027-03"' in r.text
    r = client.get("/budgets/seed?period=year&start=2027")
    assert '<option value="2027" selected>' in r.text


def test_dialog_falls_back_to_the_current_month(client, recent_spend):
    r = client.get("/budgets/seed?period=month")
    assert f'value="{date.today():%Y-%m}"' in r.text


def test_dialog_lists_spend_categories_without_income_and_transfer(client, recent_spend):
    r = client.get("/budgets/seed?period=month&start=2026-11")
    cats = [c for c, _ in _seed_rows(r.text)]
    assert cats == ["food", "fun"]
    assert 'value="30.00"' in r.text  # food: 90 / 3


def test_dialog_selects_a_category_with_an_expired_budget(client, recent_spend):
    _add(Budget(category="food", amount=400, period="month",
                start_date=date(2026, 7, 1), end_date=date(2026, 7, 31)))
    rows = dict(_seed_rows(client.get("/budgets/seed?period=month&start=2026-11").text))
    assert rows["food"] == "checked"


def test_dialog_clears_a_category_with_a_valid_budget(client, recent_spend):
    _add(Budget(category="food", amount=400, period="month", start_date=date(2026, 7, 1)))
    r = client.get("/budgets/seed?period=month&start=2026-11")
    rows = dict(_seed_rows(r.text))
    assert rows["food"] == "" and rows["fun"] == "checked"
    assert "400.00" in r.text and "2026-07-01" in r.text


def test_dialog_writes_nothing(client, recent_spend):
    client.get("/budgets/seed?period=month&start=2026-11")
    factory = get_session_factory()
    db = factory()
    assert db.query(Budget).count() == 0
    db.close()


def test_dialog_rejects_a_malformed_start(client):
    assert client.get("/budgets/seed?period=month&start=2026-1").status_code == 400


# --- 4.3 apply the dialog ----------------------------------------------------

def _post_seed(client, period, start, rows, selected):
    return client.post("/budgets/seed", data={
        "period": period, "start": start,
        "row_category": [c for c, _ in rows], "row_amount": [a for _, a in rows],
        "selected": selected,
    }, follow_redirects=False)


def test_seed_changes_only_the_selected_rows(client, app):
    _add(Budget(category="fun", amount=20, period="month", start_date=date(2026, 7, 1)))
    r = _post_seed(client, "month", "2026-11", [("food", "75.50"), ("fun", "30.00")], ["food"])
    assert r.status_code == 303
    assert r.headers["location"] == "/budgets?period=month&month=2026-11"
    assert _budgets("food") == [(date(2026, 11, 1), None, 75.5)]  # the edited amount
    assert _budgets("fun") == [(date(2026, 7, 1), None, 20.0)]   # untouched


def test_seed_override_from_the_selected_month(client, app):
    _add(Budget(category="fun", amount=20, period="month", start_date=date(2026, 7, 1)))
    _post_seed(client, "month", "2026-11", [("fun", "30.00")], ["fun"])
    assert _budgets("fun") == [(date(2026, 7, 1), date(2026, 10, 31), 20.0),
                               (date(2026, 11, 1), None, 30.0)]
    # Looking back at August still shows the old amount.
    r = client.get("/budgets?period=month&month=2026-08")
    assert "20.00" in r.text.split("<tbody>")[1]


def test_yearly_dialog_proposes_twelve_times_the_average(client, recent_spend):
    r = client.get("/budgets/seed?period=year&start=2027")
    assert 'value="360.00"' in r.text  # food: 90 / 3 * 12
    _post_seed(client, "year", "2027", [("food", "360.00")], ["food"])
    factory = get_session_factory()
    db = factory()
    created = db.query(Budget).filter(Budget.category == "food").one()
    assert (created.period, created.start_date, created.end_date) == ("year", date(2027, 1, 1), None)
    assert "annualized" in created.notes
    db.close()


def test_old_bulk_route_is_gone(client):
    assert client.post("/budgets/create-top-level").status_code in (404, 405)
