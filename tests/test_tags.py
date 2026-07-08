"""Tests for the /tags page: listing with usage counts, rename, delete.

TDD: written before implementation of api/tags.py.
"""

from __future__ import annotations

from datetime import date

import pytest

from abn_combined.core.models import CategorizationRule, Transaction
from abn_combined.db import get_session_factory


def _txn(id_, tags=None, manual_tags=None, amount=-10.0):
    return Transaction(
        id=id_,
        accountNumber="NL01",
        transactiondate=date(2024, 1, 15),
        amount=amount,
        currency="EUR",
        description="test",
        tags=tags,
        manual_tags=manual_tags,
    )


@pytest.fixture
def seed(app):
    factory = get_session_factory()
    db = factory()
    db.add(_txn("g1", tags="dining, work"))
    db.add(_txn("g2", tags="dining", manual_tags="dining, personal"))
    db.add(_txn("g3", manual_tags="work"))
    db.add(
        CategorizationRule(
            id=1,
            priority=100,
            rule_type="keyword",
            match_pattern="contains",
            match_value="test",
            category="food",
            tags="dining",
            is_active=True,
        )
    )
    db.commit()
    db.close()
    return factory


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_tags_page_renders(client):
    r = client.get("/tags")
    assert r.status_code == 200
    assert "Tags" in r.text


def test_tags_page_lists_tags_with_counts(client, seed):
    r = client.get("/tags")
    assert r.status_code == 200
    assert "dining" in r.text
    assert "work" in r.text
    assert "personal" in r.text


def test_tags_page_links_to_filtered_transactions(client, seed):
    r = client.get("/tags")
    # The filter param for tags in core/filters.py is `tag`
    assert "/transactions?tag=dining" in r.text


def test_tag_usage_counts(client, seed):
    """dining appears in g1 (tags) and g2 (tags+manual, deduped per txn) = 2 txns."""
    from abn_combined.api.tags import collect_tags

    factory = seed
    db = factory()
    tags = collect_tags(db)
    db.close()
    by_name = {t["name"]: t for t in tags}
    assert by_name["dining"]["count"] == 2  # g1 and g2 (dedup within txn)
    assert by_name["work"]["count"] == 2  # g1 and g3
    assert by_name["personal"]["count"] == 1


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


def test_tag_rename_propagates(client, seed):
    r = client.post("/tags/rename", data={"old": "dining", "new": "eating-out"})
    assert r.status_code in (200, 302, 303)

    factory = seed
    db = factory()
    g1 = db.get(Transaction, "g1")
    assert "eating-out" in g1.tags
    assert "dining" not in g1.tags
    g2 = db.get(Transaction, "g2")
    assert "eating-out" in g2.manual_tags
    rule = db.get(CategorizationRule, 1)
    assert rule.tags == "eating-out"
    db.close()


def test_tag_rename_empty_new_rejected(client, seed):
    r = client.post("/tags/rename", data={"old": "dining", "new": "  "})
    assert r.status_code in (200, 400, 422)
    # Nothing changed
    factory = seed
    db = factory()
    g1 = db.get(Transaction, "g1")
    assert "dining" in g1.tags
    db.close()


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_tag_delete_removes_from_both_columns(client, seed):
    r = client.post("/tags/delete", data={"name": "dining"})
    assert r.status_code in (200, 302, 303)

    factory = seed
    db = factory()
    g1 = db.get(Transaction, "g1")
    assert "dining" not in (g1.tags or "")
    assert "work" in g1.tags  # other tag preserved
    g2 = db.get(Transaction, "g2")
    assert g2.tags is None  # only tag removed -> None
    assert "personal" in g2.manual_tags
    assert "dining" not in g2.manual_tags
    db.close()


def test_tag_delete_leaves_other_tags(client, seed):
    client.post("/tags/delete", data={"name": "work"})
    factory = seed
    db = factory()
    g1 = db.get(Transaction, "g1")
    assert "dining" in g1.tags
    assert "work" not in g1.tags
    g3 = db.get(Transaction, "g3")
    assert g3.manual_tags is None
    db.close()
