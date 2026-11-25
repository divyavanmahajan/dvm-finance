"""Tests for the sample dataset of the web app (core and routes)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from abn_combined.core import sample_data
from abn_combined.core.models import Budget, Transaction
from abn_combined.db import get_session_factory

TODAY = date(2026, 11, 16)


@pytest.fixture
def db(client):
    session = get_session_factory()()
    yield session
    session.close()


def _real_txn(db, txn_id="real-1", **kw):
    defaults = dict(
        id=txn_id,
        accountNumber="NL01TEST0123456789",
        transactiondate=date(2026, 1, 15),
        amount=Decimal("-10.00"),
        description="Real payment",
        currency="EUR",
    )
    defaults.update(kw)
    db.add(Transaction(**defaults))
    db.commit()


# --- core -------------------------------------------------------------------


def test_load_adds_one_year_and_five_budgets(db):
    counts = sample_data.load(db, today=TODAY)
    # 11 full months of 16 items, plus the items of November up to the 16th.
    assert counts.transactions == db.query(Transaction).count()
    assert counts.budgets == 5
    assert sample_data.is_loaded(db)
    periods = sorted(b.period for b in db.query(Budget).all())
    assert periods == ["month", "month", "month", "year", "year"]
    assert all(t.id.startswith("sample-") for t in db.query(Transaction).all())
    assert max(t.transactiondate for t in db.query(Transaction).all()) <= TODAY


def test_parity_with_the_ios_dataset(db):
    """The same values as ``SampleDatasetTests`` in the iOS package."""
    counts = sample_data.load(db, today=TODAY)
    rows = {t.id: t for t in db.query(Transaction).all()}
    first = rows["sample-0"]
    last = rows[f"sample-{counts.transactions - 1}"]

    def shape(t):
        return (
            t.id,
            t.transactiondate.isoformat(),
            f"{Decimal(t.amount):.2f}",
            t.description,
            t.category,
        )

    assert counts == sample_data.Counts(transactions=PARITY_COUNT, budgets=5)
    assert shape(first) == PARITY_FIRST
    assert shape(last) == PARITY_LAST


def test_second_load_adds_nothing(db):
    sample_data.load(db, today=TODAY)
    before = db.query(Transaction).count()
    counts = sample_data.load(db, today=TODAY)
    assert counts == sample_data.Counts(transactions=0, budgets=0)
    assert db.query(Transaction).count() == before


def test_load_skips_a_budget_the_user_has(db):
    db.add(Budget(category="groceries", amount=Decimal("400"), period="month"))
    db.commit()
    counts = sample_data.load(db, today=TODAY)
    assert counts.budgets == 4
    groceries = db.query(Budget).filter(Budget.category == "groceries").all()
    assert len(groceries) == 1 and groceries[0].notes is None


def test_load_does_not_change_real_rows(db):
    _real_txn(db, category="rent", manual_category="housing")
    sample_data.load(db, today=TODAY)
    real = db.get(Transaction, "real-1")
    assert real.category == "rent" and real.manual_category == "housing"


def test_remove_deletes_only_sample_rows(db):
    _real_txn(db)
    db.add(Budget(category="rent", amount=Decimal("900"), period="month"))
    db.commit()
    loaded = sample_data.load(db, today=TODAY)
    removed = sample_data.remove(db)
    assert removed == loaded
    assert not sample_data.is_loaded(db)
    assert [t.id for t in db.query(Transaction).all()] == ["real-1"]
    assert [b.category for b in db.query(Budget).all()] == ["rent"]


def test_is_database_empty_ignores_deleted_and_merged_rows(db):
    assert sample_data.is_database_empty(db)
    _real_txn(db, "gone", deleted_at=datetime(2026, 1, 1))
    _real_txn(db, "merged", merged_into="other")
    assert sample_data.is_database_empty(db)
    _real_txn(db, "live")
    assert not sample_data.is_database_empty(db)


# Values from the iOS parity test (``SampleDatasetTests``) for 2026-11-16.
PARITY_COUNT = 186
PARITY_FIRST = ("sample-0", "2026-11-02", "-40.07", "Albert Heijn", "groceries")
PARITY_LAST = ("sample-185", "2025-12-18", "-21.33", "Apotheek", "health")


# --- routes -----------------------------------------------------------------

HX = {"HX-Request": "true"}


def test_load_route_returns_fragment_for_htmx(client, db):
    resp = client.post("/sample-data/load", headers=HX)
    assert resp.status_code == 200
    assert 'id="sample-data"' in resp.text
    assert "Remove sample data" in resp.text
    assert "Loaded" in resp.text
    assert "HX-Refresh" not in resp.headers
    assert sample_data.is_loaded(db)


def test_load_route_from_empty_transactions_page_refreshes(client):
    resp = client.post("/sample-data/load", data={"refresh": "1"}, headers=HX)
    assert resp.headers.get("HX-Refresh") == "true"


def test_routes_redirect_a_plain_form_post(client, db):
    resp = client.post(
        "/sample-data/load", headers={"referer": "/help"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/help"
    resp = client.post("/sample-data/remove", follow_redirects=False)
    assert resp.status_code == 303
    assert not sample_data.is_loaded(db)


def test_remove_route_shows_counts_and_load_control(client, db):
    sample_data.load(db)
    resp = client.post("/sample-data/remove", headers=HX)
    assert "Removed" in resp.text
    assert "Load sample data" in resp.text
    assert not sample_data.is_loaded(db)


def test_get_request_changes_nothing(client, db):
    for path in ("/sample-data/load", "/sample-data/remove"):
        assert client.get(path).status_code == 405
    assert not sample_data.is_loaded(db)


def test_transactions_page_offers_sample_data_when_empty(client, db):
    resp = client.get("/")
    assert 'id="empty-offer"' in resp.text
    assert 'href="/import"' in resp.text
    _real_txn(db)
    assert 'id="empty-offer"' not in client.get("/").text


def test_help_page_shows_the_matching_control(client, db):
    assert "Load sample data" in client.get("/help").text
    sample_data.load(db)
    assert "Remove sample data" in client.get("/help").text


def test_export_refused_while_sample_data_present(client, db, settings):
    sample_data.load(db)
    for path in ("/snapshots/export", "/snapshots/export-delta"):
        resp = client.post(path)
        assert resp.status_code == 409
        assert "Export stopped" in resp.text
        assert "Remove the sample data" in resp.text
    assert not list(settings.snapshots_dir.glob("*.json.gz"))


def test_share_refused_while_sample_data_present(client, db, settings):
    from abn_combined.core.share import get_active_share

    sample_data.load(db)
    resp = client.post("/snapshots/share", headers=HX)
    assert resp.status_code == 200
    assert "Remove the sample data" in resp.text
    assert get_active_share() is None
    assert not list(settings.snapshots_dir.glob("*.json.gz"))
