"""TestClient tests for the Transactions view: filters, pagination, sort, edits."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from abn_combined.core.filters import TransactionFilter, paginate
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
    # deterministic-ish id from the fields under test
    base.setdefault(
        "id",
        f"{base['accountNumber']}-{base['transactiondate']}-{base['amount']}-{base['description']}",
    )
    return Transaction(**base)


@pytest.fixture
def seed(app):
    """Seed a spread of transactions and return the session factory."""
    factory = get_session_factory()
    db = factory()
    txns = [
        _mk(id="t1", accountNumber="NL01", transactiondate=date(2024, 1, 5),
            amount=-25.0, description="Albert Heijn groceries", category="food"),
        _mk(id="t2", accountNumber="NL02", transactiondate=date(2024, 2, 10),
            amount=-100.0, description="Rent payment", category="housing",
            categorization_source="7"),
        _mk(id="t3", accountNumber="NL01", transactiondate=date(2024, 3, 20),
            amount=1500.0, description="Salary", category="income-salary"),
        _mk(id="t4", accountNumber="NL01", transactiondate=date(2024, 3, 25),
            amount=-8.0, description="Coffee shop", category=None,
            source_file="march.STA"),
        _mk(id="t5", accountNumber="NL02", transactiondate=date(2024, 4, 1),
            amount=-50.0, description="Restaurant dinner", category="food-restaurants",
            tags="dining, work"),
    ]
    for t in txns:
        db.add(t)
    db.commit()
    db.close()
    return factory


# ---------------------------------------------------------------------------
# Page + partial rendering
# ---------------------------------------------------------------------------


def test_index_renders(client, seed):
    r = client.get("/")
    assert r.status_code == 200
    assert "Transactions" in r.text
    assert "Albert Heijn" in r.text


def test_alias_route_renders(client, seed):
    r = client.get("/transactions")
    assert r.status_code == 200
    assert "Salary" in r.text


def test_table_partial(client, seed):
    r = client.get("/transactions/table")
    assert r.status_code == 200
    # partial: no <html> shell
    assert "<html" not in r.text.lower()
    assert "txn-table" in r.text


# ---------------------------------------------------------------------------
# Individual filter dimensions
# ---------------------------------------------------------------------------


def test_filter_q(client, seed):
    r = client.get("/transactions/table?q=albert")
    assert "Albert Heijn" in r.text
    assert "Salary" not in r.text


def test_filter_account(client, seed):
    r = client.get("/transactions/table?account=NL02")
    assert "Rent payment" in r.text
    assert "Albert Heijn" not in r.text


def test_filter_category_hierarchical(client, seed):
    # "food" matches both "food" and "food-restaurants" (hyphen separator)
    r = client.get("/transactions/table?category=food")
    assert "Albert Heijn" in r.text
    assert "Restaurant dinner" in r.text
    assert "Salary" not in r.text


def test_filter_uncategorized(client, seed):
    r = client.get("/transactions/table?category=uncategorized")
    assert "Coffee shop" in r.text
    assert "Albert Heijn" not in r.text


def test_filter_tag(client, seed):
    r = client.get("/transactions/table?tag=work")
    assert "Restaurant dinner" in r.text
    assert "Albert Heijn" not in r.text


def test_filter_amount_range(client, seed):
    r = client.get("/transactions/table?amount_min=90&amount_max=200")
    assert "Rent payment" in r.text
    assert "Coffee shop" not in r.text


def test_filter_rule_id(client, seed):
    r = client.get("/transactions/table?rule_id=7")
    assert "Rent payment" in r.text
    assert "Salary" not in r.text


def test_filter_source_file(client, seed):
    r = client.get("/transactions/table?source_file=march.STA")
    assert "Coffee shop" in r.text
    assert "Salary" not in r.text


def test_filter_date_range(client, seed):
    r = client.get("/transactions/table?date_from=2024-03-01&date_to=2024-03-31")
    assert "Salary" in r.text
    assert "Coffee shop" in r.text
    assert "Albert Heijn" not in r.text


def test_filter_combined(client, seed):
    r = client.get("/transactions/table?account=NL01&category=food")
    assert "Albert Heijn" in r.text
    assert "Restaurant dinner" not in r.text  # NL02


def test_filter_exclude_category_subtree(client, seed):
    """exclude_category=food hides food and food-* children."""
    r = client.get("/transactions/table?exclude_category=food")
    assert "Albert Heijn" not in r.text       # category="food" → excluded
    assert "Restaurant dinner" not in r.text  # category="food-restaurants" → excluded
    assert "Rent payment" in r.text
    assert "Salary" in r.text


def test_filter_exclude_keeps_uncategorized(client, seed):
    """Excluding a named category must NOT drop uncategorized rows (NULL-safe)."""
    r = client.get("/transactions/table?exclude_category=food")
    assert "Coffee shop" in r.text            # category=None → must survive


def test_filter_include_exclude_combined(client, seed):
    """include=food, exclude=food-restaurants → only exact 'food' rows show."""
    r = client.get("/transactions/table?category=food&exclude_category=food-restaurants")
    assert "Albert Heijn" in r.text           # category="food" (included, not excluded)
    assert "Restaurant dinner" not in r.text  # excluded by exclude_category


def test_ancestor_prefixes_in_known_categories(client, seed):
    """_known_categories must include ancestor prefixes (food appears because
    food-restaurants is in the DB, even if no transaction has exactly 'food')."""
    from abn_combined.api.transactions import _known_categories
    from abn_combined.db import get_session_factory

    db = get_session_factory()()
    cats = _known_categories(db)
    db.close()
    # "food" should appear as an ancestor prefix of "food-restaurants"
    assert "food" in cats
    assert "food-restaurants" in cats


# ---------------------------------------------------------------------------
# Sorting + pagination
# ---------------------------------------------------------------------------


def test_sort_amount_asc(client, seed):
    r = client.get("/transactions/table?sort=amount_asc")
    body = r.text
    # most negative (Rent -100) should appear before Salary (+1500)
    assert body.index("Rent payment") < body.index("Salary")


def test_sort_description_asc(client, seed):
    r = client.get("/transactions/table?sort=description_asc")
    body = r.text
    assert body.index("Albert Heijn groceries") < body.index("Salary")


def test_sort_tags_desc(client, seed):
    r = client.get("/transactions/table?sort=tags_desc")
    assert r.status_code == 200


def test_column_headers_are_sortable_links(client, seed):
    r = client.get("/transactions/table")
    body = r.text
    assert "sortable-th" in body
    # Clicking Date (already active desc) should link to date_asc
    assert "sort=date_asc" in body


def test_sort_toggle_asc_desc_on_repeated_click(client, seed):
    """Clicking the active column's header toggles asc <-> desc."""
    r_desc = client.get("/transactions/table?sort=amount_desc")
    assert "sort=amount_asc" in r_desc.text
    r_asc = client.get("/transactions/table?sort=amount_asc")
    assert "sort=amount_desc" in r_asc.text


def test_pagination(app, seed):
    factory = seed
    db = factory()
    # add many rows to force pagination
    for i in range(120):
        db.add(_mk(id=f"p{i}", description=f"Bulk {i}",
                   transactiondate=date(2023, 1, 1) + timedelta(days=i)))
    db.commit()
    f = TransactionFilter(page=1)
    p1 = paginate(db, f, page_size=50)
    assert len(p1.items) == 50
    assert p1.total >= 125
    assert p1.pages >= 3
    p3 = paginate(db, TransactionFilter(page=3), page_size=50)
    assert p3.page == 3
    # page beyond range clamps
    pbig = paginate(db, TransactionFilter(page=999), page_size=50)
    assert pbig.page == pbig.pages
    db.close()


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


def test_detail_partial(client, seed):
    r = client.get("/transactions/t4/detail")
    assert r.status_code == 200
    assert "march.STA" in r.text
    assert "Uncategorized" in r.text


def test_detail_404(client, seed):
    assert client.get("/transactions/nope/detail").status_code == 404


# ---------------------------------------------------------------------------
# Inline manual edit + clear (precedence semantics — Golden Principle 2)
# ---------------------------------------------------------------------------


def _reload(factory, tid) -> Transaction:
    db = factory()
    t = db.get(Transaction, tid)
    db.expunge(t)
    db.close()
    return t


def test_set_manual_category(client, seed):
    r = client.post("/transactions/t1/category", data={"manual_category": "Fun"})
    assert r.status_code == 200
    t = _reload(seed, "t1")
    assert t.manual_category == "fun"  # normalized lowercase
    assert t.category == "food"  # rule value untouched
    assert t.categorization_source == "manual"


def test_set_manual_tags(client, seed):
    client.post("/transactions/t1/tags", data={"manual_tags": "A, B"})
    t = _reload(seed, "t1")
    assert t.manual_tags == "A, B"
    assert t.categorization_source == "manual"


def test_row_response_uses_css_safe_ids_for_special_char_ids(client, app):
    """PayPal-style ids (``pp:paypaleu_...``) and ABN-style ids with dots
    contain characters that are valid HTML id values but invalid inside a
    raw CSS `#id` selector (`:` starts a pseudo-class, `.` starts a class).
    hx-target="#txn-row-{{ t.id }}" against such an id silently fails to
    match in the browser — the POST still saves, but the outerHTML swap
    never lands, so the UI looks like nothing happened. `id="txn-row-...`
    and every hx-target referencing it must go through the `css_id` filter
    so the id and its targets always match — see `app.py:_css_id`."""
    factory = get_session_factory()
    db = factory()
    db.add(_mk(id="pp:paypaleu_weird.id", description="Special char id txn"))
    db.commit()
    db.close()

    r = client.post("/transactions/pp:paypaleu_weird.id/tags", data={"manual_tags": "x"})
    assert r.status_code == 200
    body = r.text
    # The escaped form (colons/dots -> underscores) must appear as both the
    # row's own id and every hx-target that swaps into it — a mismatch
    # between the two is exactly the bug.
    escaped = "pp_paypaleu_weird_id"
    assert f'id="txn-row-{escaped}"' in body
    # hx-target must point at the <tbody id="txn-body-..."> (matching what
    # _row_response actually renders: a full <tbody> with two <tr>s), not
    # the inner <tr id="txn-row-...">  — outerHTML-swapping a <tbody>
    # fragment onto a <tr> target causes browsers to silently drop the
    # <tbody> wrapper tag, breaking the row's table layout (columns lose
    # their sizing, text wraps unpredictably) even though the swap
    # otherwise "worked".
    assert f'id="txn-body-{escaped}"' in body
    assert body.count(f'hx-target="#txn-body-{escaped}"') >= 2  # category + tags forms
    # The raw, unescaped id must NOT appear as a CSS-selector target.
    assert 'hx-target="#txn-body-pp:paypaleu_weird.id"' not in body


def test_bulk_set_tags_merges_into_existing(client, seed):
    """t5 already has rule-assigned tags "dining, work"; bulk tag must keep
    them, not replace — Golden Principle 2's "manual edits never silently
    discard state" spirit extended to bulk tagging."""
    r = client.post(
        "/transactions/bulk-tags",
        data={"transaction_ids": '["t1", "t5"]', "tags": "reviewed, 2024"},
    )
    assert r.status_code == 200
    t1 = _reload(seed, "t1")
    t5 = _reload(seed, "t5")
    assert t1.manual_tags == "reviewed, 2024"  # t1 had no prior tags
    assert t5.manual_tags == "dining, work, reviewed, 2024"  # rule tags kept
    assert t1.categorization_source == "manual"
    assert t5.categorization_source == "manual"


def test_bulk_set_tags_dedupes(client, seed):
    r = client.post(
        "/transactions/bulk-tags",
        data={"transaction_ids": '["t5"]', "tags": "work, new"},
    )
    assert r.status_code == 200
    t5 = _reload(seed, "t5")
    assert t5.manual_tags == "dining, work, new"  # "work" not duplicated


def test_bulk_set_tags_requires_ids_and_tags(client, seed):
    assert client.post(
        "/transactions/bulk-tags", data={"transaction_ids": "[]", "tags": "x"}
    ).status_code == 400
    assert client.post(
        "/transactions/bulk-tags", data={"transaction_ids": '["t1"]', "tags": ""}
    ).status_code == 400
    assert client.post(
        "/transactions/bulk-tags", data={"transaction_ids": "not json", "tags": "x"}
    ).status_code == 400


def test_clear_manual_category_restores_rule(client, seed):
    client.post("/transactions/t1/category", data={"manual_category": "Fun"})
    r = client.delete("/transactions/t1/category")
    assert r.status_code == 200
    t = _reload(seed, "t1")
    assert t.manual_category is None
    assert t.categorization_source is None  # reset since it was manual
    # effective category falls back to rule value in the rendered row
    assert "food" in r.text


def test_clear_manual_category_keeps_source_if_tags_remain(client, seed):
    client.post("/transactions/t1/category", data={"manual_category": "Fun"})
    client.post("/transactions/t1/tags", data={"manual_tags": "keepme"})
    client.delete("/transactions/t1/category")
    t = _reload(seed, "t1")
    assert t.manual_category is None
    # manual tags still present -> stay manual
    assert t.categorization_source == "manual"


def test_manual_edit_survives_rule_reapplication(client, seed):
    """Golden Principle 2: manual edits are never overwritten by rule reapply."""
    from abn_combined.core.categorizer import apply_rules

    client.post("/transactions/t1/category", data={"manual_category": "Fun"})
    db = seed()
    apply_rules(db)
    db.close()
    t = _reload(seed, "t1")
    assert t.manual_category == "fun"
    assert t.categorization_source == "manual"


def test_edit_404(client, seed):
    assert client.post("/transactions/nope/category",
                       data={"manual_category": "x"}).status_code == 404
