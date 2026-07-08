"""Unit tests for core/renames.py — rename propagation across tables.

TDD: these tests are written before the implementation.  Run them to see them
fail (ImportError or assertion errors), then implement core/renames.py to make
them green.
"""

from __future__ import annotations

from datetime import date

import pytest

from abn_combined.core.models import Budget, CategorizationRule, Transaction
from abn_combined.db import get_session_factory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _txn(id_, tags=None, manual_tags=None, category=None, manual_category=None):
    return Transaction(
        id=id_,
        accountNumber="NL01",
        transactiondate=date(2024, 1, 1),
        amount=-10.0,
        currency="EUR",
        description="test",
        tags=tags,
        manual_tags=manual_tags,
        category=category,
        manual_category=manual_category,
    )


def _rule(id_, category="food", tags=None):
    return CategorizationRule(
        id=id_,
        priority=100,
        rule_type="keyword",
        match_pattern="contains",
        match_value="test",
        category=category,
        tags=tags,
        is_active=True,
    )


# ---------------------------------------------------------------------------
# _replace_in_comma_separated unit tests
# ---------------------------------------------------------------------------


def test_replace_in_comma_separated_basic():
    from abn_combined.core.renames import _replace_in_comma_separated

    result = _replace_in_comma_separated("foo, bar, baz", "bar", "qux")
    assert result == "foo, qux, baz"


def test_replace_in_comma_separated_case_insensitive():
    from abn_combined.core.renames import _replace_in_comma_separated

    result = _replace_in_comma_separated("Foo, Bar", "foo", "new")
    assert result == "new, Bar"


def test_replace_in_comma_separated_no_match():
    from abn_combined.core.renames import _replace_in_comma_separated

    result = _replace_in_comma_separated("foo, bar", "baz", "qux")
    assert result == "foo, bar"  # unchanged


def test_replace_in_comma_separated_single():
    from abn_combined.core.renames import _replace_in_comma_separated

    result = _replace_in_comma_separated("foo", "foo", "bar")
    assert result == "bar"


def test_replace_in_comma_separated_none():
    from abn_combined.core.renames import _replace_in_comma_separated

    assert _replace_in_comma_separated(None, "foo", "bar") is None


def test_replace_in_comma_separated_empty():
    from abn_combined.core.renames import _replace_in_comma_separated

    assert _replace_in_comma_separated("", "foo", "bar") == ""


# ---------------------------------------------------------------------------
# rename_tag tests
# ---------------------------------------------------------------------------


@pytest.fixture
def db_with_tags(app):
    factory = get_session_factory()
    db = factory()
    # Two transactions with tags in both columns
    db.add(_txn("t1", tags="dining, work", manual_tags=None))
    db.add(_txn("t2", tags="grocery", manual_tags="grocery, personal"))
    db.add(_txn("t3", tags=None, manual_tags="work"))
    db.add(_txn("t4", tags="other", manual_tags=None))  # unaffected
    # Rule with tags
    db.add(_rule(1, category="food", tags="dining, work"))
    db.add(_rule(2, category="income", tags="other"))
    db.commit()
    db.close()
    return factory


def test_rename_tag_updates_transaction_tags(db_with_tags):
    from abn_combined.core.renames import rename_tag

    factory = db_with_tags
    db = factory()
    stats = rename_tag(db, "dining", "eating-out")
    db.close()

    db2 = factory()
    t1 = db2.get(Transaction, "t1")
    assert "eating-out" in t1.tags
    assert "dining" not in t1.tags
    db2.close()

    assert stats["transactions_tags"] == 1


def test_rename_tag_updates_manual_tags(db_with_tags):
    from abn_combined.core.renames import rename_tag

    factory = db_with_tags
    db = factory()
    rename_tag(db, "grocery", "groceries")
    db.close()

    db2 = factory()
    t2 = db2.get(Transaction, "t2")
    assert "groceries" in t2.tags
    assert "groceries" in t2.manual_tags
    assert "grocery" not in t2.tags
    assert "grocery" not in t2.manual_tags
    db2.close()


def test_rename_tag_updates_rule_tags(db_with_tags):
    from abn_combined.core.renames import rename_tag

    factory = db_with_tags
    db = factory()
    stats = rename_tag(db, "work", "professional")
    db.close()

    db2 = factory()
    rule = db2.get(CategorizationRule, 1)
    assert "professional" in rule.tags
    assert "work" not in rule.tags
    db2.close()

    assert stats["rules_tags"] >= 1


def test_rename_tag_preserves_other_tags(db_with_tags):
    from abn_combined.core.renames import rename_tag

    factory = db_with_tags
    db = factory()
    rename_tag(db, "dining", "eating-out")
    db.close()

    db2 = factory()
    t1 = db2.get(Transaction, "t1")
    assert "work" in t1.tags  # other tag preserved
    t4 = db2.get(Transaction, "t4")
    assert t4.tags == "other"  # unaffected
    db2.close()


def test_rename_tag_manual_precedence_intact(db_with_tags):
    """Manual tags column must survive rename without corrupting manual_category."""
    from abn_combined.core.renames import rename_tag

    factory = db_with_tags
    db = factory()
    rename_tag(db, "work", "professional")
    db.close()

    db2 = factory()
    t3 = db2.get(Transaction, "t3")
    assert t3.manual_tags == "professional"
    db2.close()


# ---------------------------------------------------------------------------
# rename_category tests
# ---------------------------------------------------------------------------


@pytest.fixture
def db_with_categories(app):
    factory = get_session_factory()
    db = factory()
    db.add(_txn("c1", category="food", manual_category=None))
    db.add(_txn("c2", category="food:restaurants", manual_category=None))
    db.add(_txn("c3", category="housing", manual_category="food"))  # manual overrides
    db.add(_txn("c4", category="income", manual_category=None))
    db.add(Budget(id=1, category="food", amount=200.0, period="month"))
    db.add(_rule(1, category="food"))
    db.add(_rule(2, category="income"))
    db.commit()
    db.close()
    return factory


def test_rename_category_updates_transaction_category(db_with_categories):
    from abn_combined.core.renames import rename_category

    factory = db_with_categories
    db = factory()
    stats = rename_category(db, "food", "groceries")
    db.close()

    db2 = factory()
    c1 = db2.get(Transaction, "c1")
    assert c1.category == "groceries"
    db2.close()
    assert stats["transactions_category"] >= 1


def test_rename_category_updates_manual_category(db_with_categories):
    from abn_combined.core.renames import rename_category

    factory = db_with_categories
    db = factory()
    rename_category(db, "food", "groceries")
    db.close()

    db2 = factory()
    c3 = db2.get(Transaction, "c3")
    assert c3.manual_category == "groceries"
    db2.close()


def test_rename_category_updates_rule(db_with_categories):
    from abn_combined.core.renames import rename_category

    factory = db_with_categories
    db = factory()
    stats = rename_category(db, "food", "groceries")
    db.close()

    db2 = factory()
    rule = db2.get(CategorizationRule, 1)
    assert rule.category == "groceries"
    db2.close()
    assert stats["rules_category"] >= 1


def test_rename_category_updates_budget(db_with_categories):
    from abn_combined.core.renames import rename_category

    factory = db_with_categories
    db = factory()
    stats = rename_category(db, "food", "groceries")
    db.close()

    db2 = factory()
    budget = db2.get(Budget, 1)
    assert budget.category == "groceries"
    db2.close()
    assert stats["budgets_category"] >= 1


def test_rename_category_normalizes_to_lowercase(db_with_categories):
    from abn_combined.core.renames import rename_category

    factory = db_with_categories
    db = factory()
    rename_category(db, "food", "Groceries")  # mixed case new value
    db.close()

    db2 = factory()
    c1 = db2.get(Transaction, "c1")
    assert c1.category == "groceries"  # normalized to lowercase
    db2.close()


def test_rename_category_does_not_touch_unrelated(db_with_categories):
    from abn_combined.core.renames import rename_category

    factory = db_with_categories
    db = factory()
    rename_category(db, "food", "groceries")
    db.close()

    db2 = factory()
    c4 = db2.get(Transaction, "c4")
    assert c4.category == "income"  # untouched
    rule2 = db2.get(CategorizationRule, 2)
    assert rule2.category == "income"  # untouched
    db2.close()
