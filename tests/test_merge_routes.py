"""Route tests of the merge of the duplicate rows.

The tests cover the preview route, the merge route, and the undo route. See
openspec/changes/unify-sepa-description-and-reference-dedup, task 8.8.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from abn_combined.core.models import MergeReport, Transaction
from abn_combined.db import get_session_factory

REFERENCE = "KFF5Q4D85TQK39G6"
ACCOUNT = "720317081"


@pytest.fixture
def db(client):
    session = get_session_factory()()
    yield session
    session.close()


def _row(db, row_id: str, **over) -> Transaction:
    values = dict(
        id=row_id,
        accountNumber=ACCOUNT,
        transactiondate=date(2024, 5, 19),
        amount=-5.75,
        description=f"the description form {row_id}",
        description_structured=json.dumps(
            {"format": "sepa", "end_to_end_reference": REFERENCE}
        ),
        currency="EUR",
        end_to_end_reference=REFERENCE,
    )
    values.update(over)
    row = Transaction(**values)
    db.add(row)
    db.commit()
    return row


def test_the_preview_page_names_each_group(client, db):
    _row(db, "aaa")
    _row(db, "bbb")

    resp = client.get("/merge")

    assert resp.status_code == 200
    assert REFERENCE in resp.text
    assert "the description form aaa" in resp.text


def test_the_preview_changes_no_row(client, db):
    """Task 8.8: the preview must change nothing."""
    _row(db, "aaa")
    _row(db, "bbb")

    client.get("/merge")

    db.expire_all()
    assert db.get(Transaction, "bbb").deleted_at is None
    assert db.get(Transaction, "bbb").merged_into is None


def test_the_page_reports_no_duplicate(client, db):
    _row(db, "aaa")

    resp = client.get("/merge")

    assert "no duplicate payment" in resp.text


def test_the_merge_needs_the_confirmation(client, db):
    """Task 8.8: the merge changes each total, so it needs a confirmation."""
    _row(db, "aaa")
    _row(db, "bbb")

    resp = client.post("/merge/run", data={}, follow_redirects=False)

    assert resp.status_code == 400
    db.expire_all()
    assert db.get(Transaction, "bbb").merged_into is None


def test_the_confirmed_merge_folds_the_group(client, db):
    _row(db, "aaa")
    _row(db, "bbb")

    resp = client.post(
        "/merge/run", data={"confirm": "yes"}, follow_redirects=False
    )

    assert resp.status_code == 303
    assert "merged=1" in resp.headers["location"]
    db.expire_all()
    assert db.get(Transaction, "bbb").merged_into == "aaa"
    assert db.get(Transaction, "aaa").deleted_at is None


def test_the_page_shows_a_refused_group(client, db):
    _row(db, "aaa", manual_category="groceries")
    _row(db, "bbb", manual_category="restaurant")

    resp = client.get("/merge")

    assert "refuses" in resp.text
    assert "groceries, restaurant" in resp.text


def test_the_undo_route_restores_the_row(client, db):
    _row(db, "aaa")
    _row(db, "bbb")
    client.post("/merge/run", data={"confirm": "yes"}, follow_redirects=False)

    resp = client.post("/merge/aaa/undo", follow_redirects=False)

    assert resp.status_code == 303
    assert "restored=1" in resp.headers["location"]
    db.expire_all()
    assert db.get(Transaction, "bbb").merged_into is None
    assert db.get(Transaction, "bbb").deleted_at is None


def test_the_page_shows_the_last_report(client, db):
    _row(db, "aaa")
    _row(db, "bbb")
    client.post("/merge/run", data={"confirm": "yes"}, follow_redirects=False)

    resp = client.get("/merge")

    assert "The last merge" in resp.text
    assert db.query(MergeReport).count() == 1


def test_the_navigation_links_to_the_merge_page(client, db):
    """The page needs a route in. Each other test reaches it by its URL.

    The link belongs to the utility menu, beside Snapshots, because the merge
    is an occasional maintenance action and not a daily tab.
    """
    resp = client.get("/transactions")

    assert resp.status_code == 200
    assert 'href="/merge"' in resp.text
    assert "Duplicates" in resp.text


def test_the_page_names_which_key_matched(client, db):
    """Task 3.4: the user sees why the system joined two rows."""
    import json as _json

    _row(db, "ref-a")
    _row(db, "ref-b")
    # A transfer pair that carries no reference, from two statement files.
    for row_id, src in (("cp-a", "fileA.STA"), ("cp-b", "fileB.STA")):
        db.add(
            Transaction(
                id=row_id,
                accountNumber=ACCOUNT,
                transactiondate=date(2025, 11, 10),
                amount=-1000.00,
                description=f"SEPA OVERBOEKING NL92ABNA8756430569 {row_id}",
                description_structured=_json.dumps(
                    {
                        "format": "sepa",
                        "iban": "NL92ABNA8756430569",
                        "end_to_end_reference": "NOTPROVIDED",
                    }
                ),
                currency="EUR",
                source_file=src,
            )
        )
    db.commit()

    resp = client.get("/merge")

    assert resp.status_code == 200
    assert "the reference" in resp.text
    assert "the counterparty" in resp.text
    # The template wraps the count onto the next line, so normalize first.
    flat = " ".join(resp.text.split())
    assert "Merge 2 transactions" in flat
