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


# ---------------------------------------------------------------------------
# Field rows (rule-editor-field-checklist)
# ---------------------------------------------------------------------------

from abn_combined.core.rule_prefill import apply_sample, build_field_rows  # noqa: E402


def _fields(rows):
    return [r["field"] for r in rows]


def _selected(rows):
    return [r["field"] for r in rows if r["selected"]]


def test_field_rows_order_and_skip_empty():
    txn = _txn(description_structured=json.dumps({
        "kenmerk": "123", "iban": "NL91ABNA0417164300", "merchant_code": "",
        "name": "J DOE", "remittance": None,
    }))
    rows, advanced = build_field_rows(txn, blank_rule_vm())
    assert _fields(rows) == ["name", "iban", "kenmerk", "description"]
    assert advanced == []


def test_field_rows_default_contains_and_sample_values():
    txn = _txn(description_structured=json.dumps({"name": "J DOE"}))
    rows, _ = build_field_rows(txn, blank_rule_vm())
    by_field = {r["field"]: r for r in rows}
    assert by_field["name"]["value"] == "J DOE"
    assert by_field["description"]["value"] == txn.description
    assert all(r["pattern"] == "contains" for r in rows)
    assert all(r["in_sample"] for r in rows)


def test_field_rows_bool_value_as_text():
    txn = _txn(description_structured=json.dumps({"is_recurring": True}))
    rows, _ = build_field_rows(txn, blank_rule_vm())
    assert {"field": "is_recurring", "value": "true"}.items() <= rows[0].items()


def test_field_rows_payer_iban_adds_iban_row():
    txn = _txn(description_structured=json.dumps({"payer_iban": "DE89370400440532013000"}))
    vm = prefill_rule_from_transaction(txn)
    rows = vm["field_rows"]
    assert "payer_iban" in _fields(rows)
    iban = next(r for r in rows if r["field"] == "iban")
    assert iban["selected"] and iban["value"] == "DE89370400440532013000"
    assert iban["in_sample"] is False


def test_draft_primary_row_keeps_draft_pattern_and_value():
    txn = _txn(description_structured=json.dumps({"name": "ACME B.V."}))
    vm = blank_rule_vm() | {"field_target": "name", "match_pattern": "exact",
                            "match_value": "ACME BV"}
    rows, _ = build_field_rows(txn, vm)
    name = next(r for r in rows if r["field"] == "name")
    assert name == {"field": "name", "value": "ACME BV", "pattern": "exact",
                    "selected": True, "in_sample": True}
    assert _selected(rows) == ["name"]


def _cond(field, value, op="AND", pattern="contains"):
    return {"field_target": field, "match_pattern": pattern, "match_value": value,
            "operator": op, "sort_order": 0}


def test_draft_leading_and_conditions_become_rows_until_or():
    txn = _txn(description_structured=json.dumps({"name": "J DOE", "kenmerk": "9"}))
    vm = blank_rule_vm() | {
        "field_target": "description", "match_value": "ALBERT",
        "conditions": [_cond("name", "DOE"), _cond("description", "PAS"),
                       _cond("kenmerk", "9", op="OR"), _cond("name", "X")],
    }
    rows, advanced = build_field_rows(txn, vm)
    assert _selected(rows) == ["name", "description"]
    assert next(r for r in rows if r["field"] == "name")["value"] == "DOE"
    # Second condition on description (already used) and everything from the
    # first OR onwards stay in the advanced builder, in their order.
    assert [(c["field_target"], c["operator"]) for c in advanced] == [
        ("description", "AND"), ("kenmerk", "OR"), ("name", "AND"),
    ]


def test_draft_field_missing_from_sample_becomes_extra_row():
    txn = _txn(description_structured=None)
    vm = blank_rule_vm() | {"field_target": "description", "match_value": "AH",
                            "conditions": [_cond("kenmerk", "123")]}
    rows, advanced = build_field_rows(txn, vm)
    assert _fields(rows) == ["description", "kenmerk"]
    kenmerk = rows[-1]
    assert kenmerk["selected"] and kenmerk["value"] == "123"
    assert kenmerk["in_sample"] is False
    assert advanced == []


def test_full_description_rule_maps_to_description_row():
    txn = _txn()
    vm = blank_rule_vm() | {"rule_type": "full_description", "field_target": "",
                            "match_value": "BEA"}
    rows, _ = build_field_rows(txn, vm)
    assert _selected(rows) == ["description"]


def test_prefill_selects_heuristic_row_and_account_filter():
    txn = _txn(description_structured=json.dumps(
        {"merchant_name": "ALBERT HEIJN", "name": "AH BV"}))
    vm = prefill_rule_from_transaction(txn)
    assert _selected(vm["field_rows"]) == ["merchant_name"]
    assert vm["filter_account"] == "NL01TEST"
    assert vm["sample_transaction_id"] == "t1"
    assert vm["sample_currency"] == "EUR"
    assert vm["conditions"] == []


def test_apply_sample_on_empty_draft_uses_heuristic():
    txn = _txn(description_structured=json.dumps({"name": "J DOE"}))
    vm = apply_sample(blank_rule_vm(), txn)
    assert _selected(vm["field_rows"]) == ["name"]
    assert vm["sample_account"] == "NL01TEST"
    assert vm["filter_account"] == ""  # a sample alone does not set a filter


def test_apply_sample_keeps_rest_of_draft():
    txn = _txn()
    vm = blank_rule_vm() | {"field_target": "description", "match_value": "AH",
                            "category": "food", "filter_currency": "USD"}
    out = apply_sample(vm, txn)
    assert out["category"] == "food"
    assert out["filter_currency"] == "USD"
