"""Route tests of the hand-entered transactions.

The tests cover the create route, the edit route, the flag route, the restore
route, the list of the flagged rows, and the purge route.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from abn_combined.constants import CASH_ACCOUNT
from abn_combined.core.models import Transaction
from abn_combined.db import get_session_factory

FUNDING_HINT = "transfer category"


@pytest.fixture
def db(client):
    session = get_session_factory()()
    yield session
    session.close()


def _seed_imported(db, txn_id="imported-1", **over):
    """Write one imported transaction. The route must refuse each edit of it."""
    values = dict(
        id=txn_id,
        accountNumber="NL01TEST0123456789",
        transactiondate=date(2026, 1, 15),
        amount=Decimal("-10.00"),
        description="Imported payment",
        currency="EUR",
    )
    values.update(over)
    db.add(Transaction(**values))
    db.commit()
    return txn_id


def _create_manual(client, **over):
    """Create one hand-entered transaction through the route."""
    form = {
        "transactiondate": "2026-02-01",
        "amount": "-20.00",
        "description": "Cash payment at the market",
        "category": "groceries",
        "tags": "cash",
    }
    form.update(over)
    return client.post("/manual/create", data=form, follow_redirects=False)


def _only_manual(db) -> Transaction:
    return db.query(Transaction).filter(Transaction.is_manual.is_(True)).one()


# ---------------------------------------------------------------------------
# The router reaches the application
# ---------------------------------------------------------------------------


def test_the_router_claims_its_paths(app):
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/manual/create" in paths
    assert "/manual/purge" in paths


# ---------------------------------------------------------------------------
# 5.1 The create route and the create form
# ---------------------------------------------------------------------------


def test_the_create_form_explains_the_funding_withdrawal(client):
    resp = client.get("/manual")
    assert resp.status_code == 200
    assert "Add a cash transaction" in resp.text
    # The spec requires the explanation of the funding withdrawal.
    assert FUNDING_HINT in resp.text
    assert "withdrawal" in resp.text


def test_the_route_accepts_the_complete_form(client, db):
    resp = _create_manual(client)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/manual")

    txn = _only_manual(db)
    assert txn.accountNumber == CASH_ACCOUNT
    assert txn.transactiondate == date(2026, 2, 1)
    assert float(txn.amount) == -20.00
    assert txn.description == "Cash payment at the market"
    assert txn.manual_category == "groceries"
    assert txn.deleted_at is None


def test_the_route_refuses_the_form_without_an_amount(client, db):
    resp = _create_manual(client, amount="")
    assert resp.status_code == 400
    assert "needs an amount" in resp.text
    # The system writes nothing.
    assert db.query(Transaction).count() == 0


def test_the_route_refuses_the_amount_of_zero(client, db):
    resp = _create_manual(client, amount="0")
    assert resp.status_code == 400
    assert "must not be zero" in resp.text
    assert db.query(Transaction).count() == 0


def test_the_route_refuses_the_form_without_a_date(client, db):
    resp = _create_manual(client, transactiondate="")
    assert resp.status_code == 400
    assert "needs a date" in resp.text
    assert db.query(Transaction).count() == 0


# ---------------------------------------------------------------------------
# 5.2 The edit route and the edit form
# ---------------------------------------------------------------------------


def test_the_route_edits_a_hand_entered_transaction(client, db):
    _create_manual(client)
    txn_id = _only_manual(db).id

    form = client.get(f"/manual/{txn_id}/edit")
    assert form.status_code == 200
    assert "Edit the cash transaction" in form.text

    resp = client.post(
        f"/manual/{txn_id}/update",
        data={
            "transactiondate": "2026-02-02",
            "amount": "-25.50",
            "description": "Cash payment at the bakery",
            "category": "groceries",
            "tags": "cash",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db.expire_all()
    txn = _only_manual(db)
    # The transaction keeps its id after the edit.
    assert txn.id == txn_id
    assert float(txn.amount) == -25.50
    assert txn.description == "Cash payment at the bakery"
    assert txn.updated_at is not None


def test_the_route_refuses_the_edit_of_an_imported_transaction(client, db):
    txn_id = _seed_imported(db)

    form = client.get(f"/manual/{txn_id}/edit")
    assert form.status_code == 400

    resp = client.post(
        f"/manual/{txn_id}/update",
        data={
            "transactiondate": "2026-02-02",
            "amount": "-99.00",
            "description": "A new description",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 400

    db.expire_all()
    txn = db.get(Transaction, txn_id)
    assert txn.description == "Imported payment"
    assert float(txn.amount) == -10.00


def test_the_route_refuses_the_edit_form_of_an_unknown_transaction(client):
    assert client.get("/manual/no-such-id/edit").status_code == 404


# ---------------------------------------------------------------------------
# 5.3 The flag route and the restore route
# ---------------------------------------------------------------------------


def test_the_route_flags_and_restores_a_hand_entered_transaction(client, db):
    _create_manual(client)
    txn_id = _only_manual(db).id

    flagged = client.post(f"/manual/{txn_id}/flag", follow_redirects=False)
    assert flagged.status_code == 303
    db.expire_all()
    # The row stays in the database, and it holds the time of the flag.
    assert db.query(Transaction).count() == 1
    assert _only_manual(db).deleted_at is not None

    restored = client.post(f"/manual/{txn_id}/restore", follow_redirects=False)
    assert restored.status_code == 303
    db.expire_all()
    assert _only_manual(db).deleted_at is None


def test_the_route_refuses_the_flag_of_an_imported_transaction(client, db):
    txn_id = _seed_imported(db)

    assert client.post(f"/manual/{txn_id}/flag",
                       follow_redirects=False).status_code == 400
    assert client.post(f"/manual/{txn_id}/restore",
                       follow_redirects=False).status_code == 400

    db.expire_all()
    assert db.get(Transaction, txn_id).deleted_at is None


# ---------------------------------------------------------------------------
# 5.4 The list of the flagged transactions
# ---------------------------------------------------------------------------


def test_the_flagged_list_shows_a_flagged_row_and_no_live_row(client, db):
    _create_manual(client, description="The flagged cash payment")
    flagged_id = _only_manual(db).id
    client.post(f"/manual/{flagged_id}/flag", follow_redirects=False)
    _create_manual(client, description="The live cash payment")

    resp = client.get("/manual/flagged")
    assert resp.status_code == 200
    assert "The flagged cash payment" in resp.text
    assert "The live cash payment" not in resp.text


# ---------------------------------------------------------------------------
# 6.2 The purge route
# ---------------------------------------------------------------------------


def _backup_files(settings):
    return list(settings.data_dir.glob("*.backup-*"))


def test_the_purge_runs_only_after_the_confirmation(client, db, settings):
    _create_manual(client, description="The first flagged payment")
    first_id = _only_manual(db).id
    client.post(f"/manual/{first_id}/flag", follow_redirects=False)
    db.expire_all()

    before = len(_backup_files(settings))

    # No confirmation: the system deletes nothing and writes no backup.
    refused = client.post("/manual/purge", data={}, follow_redirects=False)
    assert refused.status_code == 400
    assert "Confirm the purge first" in refused.text
    db.expire_all()
    assert db.query(Transaction).count() == 1
    assert len(_backup_files(settings)) == before

    # The confirmation: the system deletes the flagged row and reports one.
    done = client.post(
        "/manual/purge", data={"confirm": "yes"}, follow_redirects=False
    )
    assert done.status_code == 303
    assert done.headers["location"] == "/manual/flagged?purged=1"
    db.expire_all()
    assert db.query(Transaction).count() == 0
    assert len(_backup_files(settings)) > before


def test_the_purge_deletes_no_live_row(client, db):
    _create_manual(client, description="The flagged payment")
    flagged_id = _only_manual(db).id
    client.post(f"/manual/{flagged_id}/flag", follow_redirects=False)
    _create_manual(client, description="The live payment")
    _seed_imported(db)

    done = client.post(
        "/manual/purge", data={"confirm": "yes"}, follow_redirects=False
    )
    assert done.headers["location"] == "/manual/flagged?purged=1"
    db.expire_all()
    descriptions = {t.description for t in db.query(Transaction).all()}
    assert descriptions == {"The live payment", "Imported payment"}


def test_the_flagged_page_reports_the_purged_count(client):
    resp = client.get("/manual/flagged?purged=2")
    assert resp.status_code == 200
    assert "The purge deleted 2 transactions." in resp.text
    one = client.get("/manual/flagged?purged=1")
    assert "The purge deleted 1 transaction." in one.text


def test_the_flagged_page_warns_before_the_control(client):
    resp = client.get("/manual/flagged")
    body = resp.text
    assert "cannot undo the purge" in body
    # The warning comes before the control.
    assert body.index("cannot undo the purge") < body.index("Purge now")


def test_a_hand_entered_row_carries_the_edit_time(client, db):
    _create_manual(client)
    txn = _only_manual(db)
    assert isinstance(txn.updated_at, datetime)


def test_the_detail_view_links_to_the_edit_page_of_a_cash_row(client):
    """The user reaches the edit page from the detail view of a cash row.

    Without the link, the route has no entry point, and the user must type the
    URL.
    """
    from abn_combined.core.manual_txn import create_manual_transaction
    from abn_combined.db import get_session_factory

    session_factory = get_session_factory()
    with session_factory() as db:
        row = create_manual_transaction(
            db,
            transactiondate=date(2026, 4, 1),
            amount=-4.00,
            description="Detail link check",
        )
        txn_id = row.id

    html = client.get(f"/transactions/{txn_id}/detail").text
    assert f"/manual/{txn_id}/edit" in html
    assert "Cash payment" in html
