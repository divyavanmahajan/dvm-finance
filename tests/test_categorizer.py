"""Rule engine, preview, and change-report tests."""

from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from abn_combined.core.categorizer import (
    RuleValidationError,
    _apply_rule_to_transaction,
    apply_rules,
    preview_rule,
    record_rule_change,
    rule_snapshot,
    validate_rule_regex,
)
from abn_combined.core.models import (
    Base,
    CategorizationRule,
    RuleChangeItem,
    RuleChangeReport,
    RuleCondition,
    Transaction,
)


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def add_rule(session, **kw):
    kw.setdefault("rule_type", "keyword")
    kw.setdefault("match_pattern", "contains")
    kw.setdefault("field_target", "description")
    rule = CategorizationRule(**kw)
    session.add(rule)
    session.commit()
    return rule


def add_txn(session, tid, description, **kw):
    kw.setdefault("accountNumber", "ACC")
    kw.setdefault("transactiondate", date(2024, 1, 1))
    kw.setdefault("amount", -1.0)
    kw.setdefault("currency", "EUR")
    txn = Transaction(id=tid, description=description, **kw)
    session.add(txn)
    session.commit()
    return txn


# --- match pattern matrix (keyword rule) ---------------------------------

@pytest.mark.parametrize(
    "pattern,value,desc,expected",
    [
        ("contains", "supermarkt", "AH SUPERMARKT NL", True),
        ("contains", "supermarkt", "restaurant", False),
        ("exact", "ah supermarkt", "AH SUPERMARKT", True),
        ("exact", "ah", "AH SUPERMARKT", False),
        ("starts_with", "ah", "AH SUPERMARKT", True),
        ("starts_with", "super", "AH SUPERMARKT", False),
        ("ends_with", "nl", "AH SUPERMARKT NL", True),
        ("ends_with", "ah", "AH SUPERMARKT NL", False),
        ("regex", r"super.*markt", "AH SUPERMARKT", True),
        ("regex", r"^zzz", "AH SUPERMARKT", False),
    ],
)
def test_keyword_match_patterns(pattern, value, desc, expected):
    rule = CategorizationRule(
        rule_type="keyword",
        match_pattern=pattern,
        field_target="description",
        match_value=value,
        category="c",
    )
    assert _apply_rule_to_transaction(rule, {"description": desc}) is expected


# --- rule types ----------------------------------------------------------

def test_full_description_rule():
    rule = CategorizationRule(
        rule_type="full_description",
        match_pattern="contains",
        field_target=None,
        match_value="netflix",
        category="entertainment",
    )
    assert _apply_rule_to_transaction(rule, {"description": "SEPA NETFLIX INTL"})


def test_structured_field_rule():
    rule = CategorizationRule(
        rule_type="structured_field",
        match_pattern="exact",
        field_target="format",
        match_value="sepa",
        category="transfer",
    )
    trans = {"description": "x", "description_structured": json.dumps({"format": "sepa"})}
    assert _apply_rule_to_transaction(rule, trans)
    trans_pos = {"description": "x", "description_structured": json.dumps({"format": "pos"})}
    assert not _apply_rule_to_transaction(rule, trans_pos)


def test_account_iban_rule_exact_and_from_description():
    rule = CategorizationRule(
        rule_type="account_iban",
        match_pattern="exact",
        field_target="iban",
        match_value="NL04ABNA0252265866",
        category="transfer",
    )
    trans = {"description": "x", "description_structured": json.dumps({"iban": "NL04ABNA0252265866"})}
    assert _apply_rule_to_transaction(rule, trans)
    # IBAN extracted from raw description text.
    trans2 = {"description": "SEPA OVERBOEKING IBAN: NL04ABNA0252265866 NAAM: X"}
    assert _apply_rule_to_transaction(rule, trans2)


# --- conditions AND/OR ---------------------------------------------------

def test_and_condition():
    rule = CategorizationRule(
        rule_type="keyword", match_pattern="contains", field_target="description",
        match_value="albert", category="groceries",
    )
    rule.conditions.append(
        RuleCondition(field_target="description", match_pattern="contains", match_value="heijn", operator="AND")
    )
    assert _apply_rule_to_transaction(rule, {"description": "ALBERT HEIJN"})
    assert not _apply_rule_to_transaction(rule, {"description": "ALBERT CUYP"})


def test_or_condition():
    # Ported semantics: the primary condition must match first; additional
    # conditions are folded into ``running`` which starts True, so an OR condition
    # never blocks a rule (True or X == True) and only AND conditions can narrow it.
    rule = CategorizationRule(
        rule_type="keyword", match_pattern="contains", field_target="description",
        match_value="jumbo", category="groceries",
    )
    rule.conditions.append(
        RuleCondition(field_target="description", match_pattern="contains", match_value="lidl", operator="OR")
    )
    # Primary matches -> rule matches even though the OR condition ("lidl") does not.
    assert _apply_rule_to_transaction(rule, {"description": "JUMBO CITY"})
    # Primary does not match -> rule does not match regardless of the OR condition.
    assert not _apply_rule_to_transaction(rule, {"description": "LIDL STORE"})


def test_or_rescues_failed_and_condition():
    # OR after an AND: running = (True and False) or True = True.
    rule = CategorizationRule(
        rule_type="keyword", match_pattern="contains", field_target="description",
        match_value="jumbo", category="groceries",
    )
    rule.conditions.append(
        RuleCondition(field_target="description", match_pattern="contains", match_value="zzz", operator="AND", sort_order=0)
    )
    rule.conditions.append(
        RuleCondition(field_target="description", match_pattern="contains", match_value="city", operator="OR", sort_order=1)
    )
    assert _apply_rule_to_transaction(rule, {"description": "JUMBO CITY"})


# --- context filters -----------------------------------------------------

def test_filter_account():
    rule = CategorizationRule(
        rule_type="keyword", match_pattern="contains", field_target="description",
        match_value="pay", category="c", filter_account="ACC1",
    )
    assert _apply_rule_to_transaction(rule, {"description": "PAY", "accountNumber": "ACC1"})
    assert not _apply_rule_to_transaction(rule, {"description": "PAY", "accountNumber": "ACC2"})


def test_filter_currency_and_date():
    rule = CategorizationRule(
        rule_type="keyword", match_pattern="contains", field_target="description",
        match_value="pay", category="c", filter_currency="USD",
        filter_date_from=date(2024, 1, 1), filter_date_to=date(2024, 12, 31),
    )
    assert _apply_rule_to_transaction(
        rule, {"description": "PAY", "currency": "USD", "transactiondate": date(2024, 6, 1)}
    )
    assert not _apply_rule_to_transaction(
        rule, {"description": "PAY", "currency": "EUR", "transactiondate": date(2024, 6, 1)}
    )
    assert not _apply_rule_to_transaction(
        rule, {"description": "PAY", "currency": "USD", "transactiondate": date(2023, 6, 1)}
    )


# --- apply_rules ---------------------------------------------------------

def test_apply_rules_sets_category_and_source(session):
    rule = add_rule(session, match_value="supermarkt", category="Groceries")
    add_txn(session, "t1", "AH SUPERMARKT")
    changes = apply_rules(session)
    assert len(changes) == 1
    txn = session.get(Transaction, "t1")
    assert txn.category == "groceries"  # lowercased
    assert txn.categorization_source == str(rule.id)


def test_apply_rules_no_match_is_none(session):
    add_rule(session, match_value="zzz", category="c")
    add_txn(session, "t1", "AH SUPERMARKT", category="stale", categorization_source="9")
    apply_rules(session)
    txn = session.get(Transaction, "t1")
    assert txn.category is None
    assert txn.categorization_source is None


def test_apply_rules_priority_lower_wins(session):
    add_rule(session, priority=50, match_value="shop", category="high")
    add_rule(session, priority=10, match_value="shop", category="low")
    add_txn(session, "t1", "THE SHOP")
    apply_rules(session)
    assert session.get(Transaction, "t1").category == "low"


def test_apply_rules_never_touches_manual(session):
    add_rule(session, match_value="supermarkt", category="groceries")
    add_txn(
        session, "t1", "AH SUPERMARKT",
        manual_category="dining", manual_tags="mine",
        category="old", tags="oldtag", categorization_source="manual",
    )
    apply_rules(session)
    txn = session.get(Transaction, "t1")
    assert txn.manual_category == "dining"
    assert txn.manual_tags == "mine"
    assert txn.categorization_source == "manual"
    assert txn.category == "old"  # untouched because manual


def test_apply_rules_assigns_tags(session):
    add_rule(session, match_value="netflix", category="entertainment", tags="subscription")
    add_txn(session, "t1", "NETFLIX")
    apply_rules(session)
    assert session.get(Transaction, "t1").tags == "subscription"


# --- tag-only rules --------------------------------------------------------

def test_tag_only_rule_applies_after_category_rules(session):
    add_rule(session, match_value="supermarkt", category="groceries")
    add_rule(
        session, match_value="ah ", category=None, tags="ah-brand",
        is_tag_only=True, priority=1,  # highest priority, but tag-only so it must not win category
    )
    add_txn(session, "t1", "AH SUPERMARKT")
    apply_rules(session)
    txn = session.get(Transaction, "t1")
    # Category comes from the category rule, not the (higher-priority) tag-only rule.
    assert txn.category == "groceries"
    assert txn.tags == "ah-brand"


def test_multiple_tag_only_rules_all_apply(session):
    add_rule(session, match_value="supermarkt", category="groceries")
    add_rule(session, match_value="ah ", category=None, tags="brand-ah", is_tag_only=True)
    add_rule(session, match_value="supermarkt", category=None, tags="essential", is_tag_only=True)
    add_txn(session, "t1", "AH SUPERMARKT")
    apply_rules(session)
    txn = session.get(Transaction, "t1")
    assert txn.category == "groceries"
    tags = set(txn.tags.split(","))
    assert tags == {"brand-ah", "essential"}


def test_tag_only_rule_applies_to_manually_categorized_transactions(session):
    add_rule(session, match_value="ah ", category=None, tags="brand-ah", is_tag_only=True)
    add_txn(
        session, "t1", "AH SUPERMARKT",
        manual_category="dining", category="old",
        categorization_source="manual",
    )
    apply_rules(session)
    txn = session.get(Transaction, "t1")
    # Category (manual) is untouched, but the tag-only rule still applies its tag.
    assert txn.manual_category == "dining"
    assert txn.category == "old"
    assert txn.tags == "brand-ah"


def test_tag_only_rule_merges_with_existing_tags_without_duplicates(session):
    add_rule(session, match_value="netflix", category="entertainment", tags="subscription")
    add_rule(session, match_value="netflix", category=None, tags="subscription,streaming", is_tag_only=True)
    add_txn(session, "t1", "NETFLIX")
    apply_rules(session)
    txn = session.get(Transaction, "t1")
    assert txn.category == "entertainment"
    assert set(txn.tags.split(",")) == {"subscription", "streaming"}


# --- preview -------------------------------------------------------------

def test_preview_new_rule_gains_and_changes(session):
    add_txn(session, "t1", "SPOTIFY PREMIUM")
    add_txn(session, "t2", "GROCERY RUN")
    draft = CategorizationRule(
        rule_type="keyword", match_pattern="contains", field_target="description",
        match_value="spotify", category="music",
    )
    result = preview_rule(session, draft)
    assert result.matched == ["t1"]
    assert result.gains == ["t1"]
    assert result.losses == []
    assert [c.transaction_id for c in result.changes] == ["t1"]
    assert result.changes[0].new_category == "music"


def test_preview_edit_reports_losses(session):
    rule = add_rule(session, match_value="spotify", category="music")
    add_txn(session, "t1", "SPOTIFY")
    apply_rules(session)  # t1 attributed to rule
    assert session.get(Transaction, "t1").categorization_source == str(rule.id)

    # Edit the rule so it no longer matches SPOTIFY.
    draft = CategorizationRule(
        id=rule.id, rule_type="keyword", match_pattern="contains",
        field_target="description", match_value="netflix", category="music",
    )
    result = preview_rule(session, draft, existing_rule_id=rule.id)
    assert "t1" in result.losses
    assert result.matched == []
    # Preview performs no writes.
    assert session.get(Transaction, "t1").category == "music"


def test_preview_invalid_regex_raises(session):
    draft = CategorizationRule(
        rule_type="keyword", match_pattern="regex", field_target="description",
        match_value="[unclosed", category="c",
    )
    with pytest.raises(RuleValidationError):
        preview_rule(session, draft)


# --- regex validation ----------------------------------------------------

def test_validate_rule_regex_ok():
    rule = CategorizationRule(
        rule_type="keyword", match_pattern="regex", field_target="description",
        match_value=r"super.*markt", category="c",
    )
    validate_rule_regex(rule)  # no raise


def test_validate_rule_regex_condition_invalid():
    rule = CategorizationRule(
        rule_type="keyword", match_pattern="contains", field_target="description",
        match_value="x", category="c",
    )
    rule.conditions.append(
        RuleCondition(field_target="description", match_pattern="regex", match_value="(bad")
    )
    with pytest.raises(RuleValidationError):
        validate_rule_regex(rule)


# --- record_rule_change --------------------------------------------------

def test_record_rule_change_persists_report_and_items(session):
    add_txn(session, "t1", "SPOTIFY")
    add_txn(session, "t2", "NETFLIX")
    rule = add_rule(session, match_value="spotify", category="music")

    report = record_rule_change(
        session, action="create", after=rule_snapshot(rule),
        rule_id=rule.id, rule_uuid=rule.uuid,
    )
    stored = session.get(RuleChangeReport, report.id)
    assert stored.action == "create"
    assert stored.rule_id == rule.id
    assert stored.summary["changed"] == 1
    items = session.query(RuleChangeItem).filter_by(report_id=report.id).all()
    assert len(items) == 1
    assert items[0].transaction_id == "t1"
    assert items[0].new_category == "music"
    assert items[0].old_category is None


def test_record_rule_change_recategorize_action(session):
    add_txn(session, "t1", "SPOTIFY")
    add_rule(session, match_value="spotify", category="music")
    report = record_rule_change(session, action="recategorize")
    assert report.action == "recategorize"
    assert report.summary["changed"] == 1


def test_rule_snapshot_none():
    assert rule_snapshot(None) is None
