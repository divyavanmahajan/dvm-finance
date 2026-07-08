"""Tests for cash-flow aggregation (core/cash_flow.py) and the /cash-flow route.

TDD: written before implementation.
"""

from __future__ import annotations

from datetime import date

import pytest

from abn_combined.core.models import Transaction
from abn_combined.db import get_session_factory


def _txn(id_, amount, txdate, category=None, manual_category=None, account="NL01"):
    return Transaction(
        id=id_,
        accountNumber=account,
        transactiondate=txdate,
        amount=amount,
        currency="EUR",
        description="test",
        category=category,
        manual_category=manual_category,
    )


# ---------------------------------------------------------------------------
# generate_periods
# ---------------------------------------------------------------------------


class TestGeneratePeriods:
    def test_month_periods(self):
        from abn_combined.core.cash_flow import generate_periods

        periods = generate_periods(date(2024, 1, 15), date(2024, 3, 10), "month")
        assert len(periods) == 3
        assert periods[0][0] == date(2024, 1, 1)
        assert periods[0][1] == date(2024, 1, 31)
        assert periods[2][1] == date(2024, 3, 10)  # clamped to end
        assert periods[0][2] == "Jan 2024"

    def test_year_periods(self):
        from abn_combined.core.cash_flow import generate_periods

        periods = generate_periods(date(2023, 5, 1), date(2024, 2, 1), "year")
        assert len(periods) == 2
        assert periods[0][2] == "2023"
        assert periods[1][2] == "2024"

    def test_week_periods(self):
        from abn_combined.core.cash_flow import generate_periods

        # 2024-01-15 is a Monday
        periods = generate_periods(date(2024, 1, 16), date(2024, 1, 28), "week")
        assert periods[0][0] == date(2024, 1, 15)  # snapped to Monday
        assert periods[0][1] == date(2024, 1, 21)
        assert len(periods) == 2


# ---------------------------------------------------------------------------
# aggregate cash flow
# ---------------------------------------------------------------------------


class TestCashFlowAggregation:
    @pytest.fixture
    def seeded(self, app):
        factory = get_session_factory()
        db = factory()
        # Jan: income 1500, expenses 25+100 = 125 -> net 1375
        db.add(_txn("cf1", 1500.0, date(2024, 1, 20), category="income:salary"))
        db.add(_txn("cf2", -25.0, date(2024, 1, 5), category="food"))
        db.add(_txn("cf3", -100.0, date(2024, 1, 10), category="housing"))
        # Feb: income 0, expense 50 -> net -50
        db.add(_txn("cf4", -50.0, date(2024, 2, 14), category="food"))
        # Different account, Feb: income 200
        db.add(_txn("cf5", 200.0, date(2024, 2, 20), category="income", account="NL02"))
        db.commit()
        db.close()
        return factory

    def test_monthly_aggregation_hand_computed(self, seeded):
        from abn_combined.core.cash_flow import compute_cash_flow

        factory = seeded
        db = factory()
        result = compute_cash_flow(
            db, date_from=date(2024, 1, 1), date_to=date(2024, 2, 29), breakdown="month"
        )
        db.close()

        assert len(result.periods) == 2
        # Jan: income 1500, expense 125, net 1375
        assert result.income[0] == pytest.approx(1500.0, abs=0.01)
        assert result.expense[0] == pytest.approx(125.0, abs=0.01)
        assert result.net[0] == pytest.approx(1375.0, abs=0.01)
        # Feb: income 200 (NL02), expense 50, net 150
        assert result.income[1] == pytest.approx(200.0, abs=0.01)
        assert result.expense[1] == pytest.approx(50.0, abs=0.01)
        assert result.net[1] == pytest.approx(150.0, abs=0.01)

    def test_account_filter(self, seeded):
        from abn_combined.core.cash_flow import compute_cash_flow

        factory = seeded
        db = factory()
        result = compute_cash_flow(
            db,
            date_from=date(2024, 1, 1),
            date_to=date(2024, 2, 29),
            breakdown="month",
            accounts=["NL01"],
        )
        db.close()
        # Feb income for NL01 only = 0 (cf5 is NL02)
        assert result.income[1] == pytest.approx(0.0, abs=0.01)
        assert result.expense[1] == pytest.approx(50.0, abs=0.01)

    def test_manual_category_precedence_transfer_exclusion(self, app):
        """Transfers (effective category) are excluded from cash flow."""
        from abn_combined.core.cash_flow import compute_cash_flow

        factory = get_session_factory()
        db = factory()
        db.add(_txn("tr1", -500.0, date(2024, 1, 5), category="transfer"))
        db.add(
            _txn(
                "tr2",
                -300.0,
                date(2024, 1, 6),
                category="food",
                manual_category="transfer",  # manual override to transfer
            )
        )
        db.add(_txn("tr3", -50.0, date(2024, 1, 7), category="food"))
        db.commit()
        result = compute_cash_flow(
            db, date_from=date(2024, 1, 1), date_to=date(2024, 1, 31), breakdown="month"
        )
        db.close()
        # Only tr3 counted; tr1 and tr2 are transfers
        assert result.expense[0] == pytest.approx(50.0, abs=0.01)

    def test_totals_row(self, seeded):
        from abn_combined.core.cash_flow import compute_cash_flow

        factory = seeded
        db = factory()
        result = compute_cash_flow(
            db, date_from=date(2024, 1, 1), date_to=date(2024, 2, 29), breakdown="month"
        )
        db.close()
        assert result.total_income == pytest.approx(1700.0, abs=0.01)
        assert result.total_expense == pytest.approx(175.0, abs=0.01)
        assert result.total_net == pytest.approx(1525.0, abs=0.01)


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


def test_cash_flow_page_renders(client):
    r = client.get("/cash-flow")
    assert r.status_code == 200
    assert "Cash Flow" in r.text


def test_cash_flow_page_with_data(client, app):
    factory = get_session_factory()
    db = factory()
    db.add(_txn("r1", 1000.0, date(2024, 1, 15), category="income"))
    db.add(_txn("r2", -200.0, date(2024, 1, 20), category="food"))
    db.commit()
    db.close()

    r = client.get("/cash-flow?date_from=2024-01-01&date_to=2024-01-31")
    assert r.status_code == 200
    assert "1000" in r.text or "1,000" in r.text


def test_cash_flow_account_filter_param(client, app):
    factory = get_session_factory()
    db = factory()
    db.add(_txn("r3", -100.0, date(2024, 1, 10), category="food", account="NL09"))
    db.commit()
    db.close()

    r = client.get("/cash-flow?account=NL09&date_from=2024-01-01&date_to=2024-01-31")
    assert r.status_code == 200


def test_cash_flow_links_to_transactions(client, app):
    factory = get_session_factory()
    db = factory()
    db.add(_txn("r4", -75.0, date(2024, 3, 5), category="food"))
    db.commit()
    db.close()

    r = client.get("/cash-flow?date_from=2024-03-01&date_to=2024-03-31")
    assert r.status_code == 200
    # Amounts link to the filtered transactions view
    assert "/transactions?" in r.text
