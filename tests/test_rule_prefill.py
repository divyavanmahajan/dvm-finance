"""Unit tests for create-rule-from-transaction prefill heuristics."""

from __future__ import annotations

import json
from datetime import date

from abn_combined.core.models import Transaction
from abn_combined.core.rule_prefill import blank_rule_vm, prefill_rule_from_transaction


def _txn(**kw) -> Transaction:
    base = dict(
        id="t1",
        accountNumber="NL01TEST",
        transactiondate=date(2024, 5, 1),
        amount=-12.5,
        currency="EUR",
        description="BEA, Apple Pay ALBERT HEIJN 1234,PAS123",
    )
    base.update(kw)
    return Transaction(**base)


def test_blank_vm_defaults():
    vm = blank_rule_vm()
    assert vm["rule_type"] == "keyword"
    assert vm["match_pattern"] == "contains"
    assert vm["field_target"] == "description"
    assert vm["priority"] == 100
    assert vm["is_active"] is True
    assert vm["conditions"] == []


def test_prefill_merchant_name_takes_priority():
    txn = _txn(description_structured=json.dumps(
        {"merchant_name": "ALBERT HEIJN", "name": "AH BV", "iban": "NL91ABNA0417164300"}
    ))
    vm = prefill_rule_from_transaction(txn)
    assert vm["rule_type"] == "structured_field"
    assert vm["field_target"] == "merchant_name"
    assert vm["match_value"] == "ALBERT HEIJN"


def test_prefill_name_when_no_merchant():
    txn = _txn(description_structured=json.dumps({"name": "J DOE", "iban": "NL91ABNA0417164300"}))
    vm = prefill_rule_from_transaction(txn)
    assert vm["rule_type"] == "structured_field"
    assert vm["field_target"] == "name"
    assert vm["match_value"] == "J DOE"


def test_prefill_iban_when_no_name_fields():
    txn = _txn(description_structured=json.dumps({"iban": "NL91ABNA0417164300"}))
    vm = prefill_rule_from_transaction(txn)
    assert vm["rule_type"] == "account_iban"
    assert vm["field_target"] == "iban"
    assert vm["match_value"] == "NL91ABNA0417164300"


def test_prefill_payer_iban_fallback():
    txn = _txn(description_structured=json.dumps({"payer_iban": "DE89370400440532013000"}))
    vm = prefill_rule_from_transaction(txn)
    assert vm["rule_type"] == "account_iban"
    assert vm["match_value"] == "DE89370400440532013000"


def test_prefill_description_fallback():
    txn = _txn(description_structured=None)
    vm = prefill_rule_from_transaction(txn)
    assert vm["rule_type"] == "keyword"
    assert vm["field_target"] == "description"
    assert vm["match_value"] == txn.description


def test_prefill_bad_structured_json_falls_back_to_description():
    txn = _txn(description_structured="{not json")
    vm = prefill_rule_from_transaction(txn)
    assert vm["rule_type"] == "keyword"
    assert vm["match_value"] == txn.description


def test_prefill_account_filter_and_category():
    txn = _txn(category="food:groceries, misc")
    vm = prefill_rule_from_transaction(txn)
    assert vm["filter_account"] == "NL01TEST"
    assert vm["category"] == "food:groceries"  # first category only


def test_prefill_manual_category_wins():
    txn = _txn(category="food", manual_category="groceries")
    vm = prefill_rule_from_transaction(txn)
    assert vm["category"] == "groceries"


def test_prefill_notes_mention_transaction():
    txn = _txn()
    vm = prefill_rule_from_transaction(txn)
    assert "Created from transaction" in vm["notes"]
