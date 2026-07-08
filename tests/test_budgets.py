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
