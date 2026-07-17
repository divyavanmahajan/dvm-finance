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


def test_budgets_page_defaults_add_form_dates_to_current_month(client):
    """Valid from/to on the "Add budget" form must default to the current
    month's start/end, not be left blank."""
    from abn_combined.core.budget_report import get_period_dates

    start, end = get_period_dates("month", date.today())
    r = client.get("/budgets")
    assert r.status_code == 200
    assert f'value="{start.isoformat()}"' in r.text
    assert f'value="{end.isoformat()}"' in r.text


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


def test_create_top_level_budgets(client, app):
    """One month budget per top-level category, amount = 3-month average."""
    factory = get_session_factory()
    db = factory()
    ref = date.today().replace(day=15)
    prev_year, prev_month = (ref.year, ref.month - 1) if ref.month > 1 else (ref.year - 1, 12)
    db.add(_txn("c1", -80.0, category="food-groceries", txdate=date(prev_year, prev_month, 5)))
    db.commit()
    db.close()

    r = client.post("/budgets/create-top-level")
    assert r.status_code in (200, 302, 303)

    db2 = factory()
    created = db2.query(Budget).filter(Budget.category == "food", Budget.period == "month").first()
    db2.close()
    assert created is not None
    assert float(created.amount) == pytest.approx(80.0 / 3, abs=0.01)


def test_create_top_level_budgets_yearly_annualized(client, app):
    """Yearly seeding creates year-period budgets whose amount is 12× the
    3-month monthly average, valid for the full current calendar year."""
    from abn_combined.core.budget_report import get_period_dates

    factory = get_session_factory()
    db = factory()
    ref = date.today().replace(day=15)
    prev_year, prev_month = (ref.year, ref.month - 1) if ref.month > 1 else (ref.year - 1, 12)
    db.add(_txn("y1", -90.0, category="food-groceries", txdate=date(prev_year, prev_month, 5)))
    db.commit()
    db.close()

    r = client.post("/budgets/create-top-level", data={"period": "year"})
    assert r.status_code in (200, 302, 303)

    db2 = factory()
    created = db2.query(Budget).filter(Budget.category == "food", Budget.period == "year").first()
    db2.close()
    assert created is not None
    # 3-month average = 90 / 3 = 30, annualized = 30 * 12 = 360
    assert float(created.amount) == pytest.approx(360.0, abs=0.01)
    year_start, year_end = get_period_dates("year", date.today())
    assert created.start_date == year_start
    assert created.end_date == year_end
    assert "annualized" in (created.notes or "")


def test_create_top_level_budgets_monthly_default(client, app):
    """Monthly seeding (no/period=month) still creates month-period budgets
    valid for the current month window, unannualized amount."""
    from abn_combined.core.budget_report import get_period_dates

    factory = get_session_factory()
    db = factory()
    ref = date.today().replace(day=15)
    prev_year, prev_month = (ref.year, ref.month - 1) if ref.month > 1 else (ref.year - 1, 12)
    db.add(_txn("mo1", -90.0, category="food-groceries", txdate=date(prev_year, prev_month, 5)))
    db.commit()
    db.close()

    client.post("/budgets/create-top-level", data={"period": "month"})

    db2 = factory()
    created = db2.query(Budget).filter(Budget.category == "food", Budget.period == "month").first()
    db2.close()
    assert created is not None
    assert float(created.amount) == pytest.approx(30.0, abs=0.01)  # 90/3, not annualized
    month_start, month_end = get_period_dates("month", date.today())
    assert created.start_date == month_start
    assert created.end_date == month_end


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


def test_create_top_level_budgets_skips_existing(client, app):
    """A top-level category that already has a month budget is left alone —
    the bulk action never overwrites a budget the user already set."""
    factory = get_session_factory()
    db = factory()
    db.add(Budget(id=60, category="food", amount=999.0, period="month"))
    db.add(_txn("c2", -80.0, category="food-groceries", txdate=date(2024, 1, 5)))
    db.commit()
    db.close()

    client.post("/budgets/create-top-level")

    db2 = factory()
    budgets = db2.query(Budget).filter(Budget.category == "food", Budget.period == "month").all()
    db2.close()
    assert len(budgets) == 1
    assert float(budgets[0].amount) == pytest.approx(999.0, abs=0.01)  # untouched


def test_create_top_level_budgets_skips_categories_with_no_recent_spend(client, app):
    """A category whose only spend is outside the averaging window (e.g. a
    single transaction from over a year ago) proposes nothing to create."""
    factory = get_session_factory()
    db = factory()
    db.add(_txn("old", -80.0, category="stale-cat", txdate=date(2020, 1, 5)))
    db.commit()
    db.close()

    client.post("/budgets/create-top-level")

    db2 = factory()
    assert db2.query(Budget).filter(Budget.category == "stale").count() == 0
    db2.close()
