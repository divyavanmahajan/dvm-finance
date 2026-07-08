"""Heuristics to pre-fill a categorization rule from an existing transaction.

Ported from the legacy ``static/js/transactions.js`` ``createRuleFromTransaction``
logic (structured-field priority merchant_name > name > iban, else description).
Given one :class:`Transaction`, produce a rule "form view-model" dict that the
editor template and the preview endpoint both understand.
"""

from __future__ import annotations

import json
from typing import Any

from .models import Transaction

# Priority order of structured fields to key a rule on (highest first). Mirrors the
# legacy JS heuristic; ``iban``/``payer_iban`` fall through to an account_iban rule.
_STRUCTURED_PRIORITY = ("merchant_name", "name", "counterparty")


def _parse_structured(txn: Transaction) -> dict[str, Any]:
    raw = txn.description_structured
    if not raw:
        return {}
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _first_category(txn: Transaction) -> str:
    value = txn.manual_category or txn.category or ""
    if not value:
        return ""
    return value.split(",")[0].strip()


def blank_rule_vm() -> dict[str, Any]:
    """Default view-model for a brand-new (non-prefilled) rule."""
    return {
        "id": None,
        "uuid": None,
        "priority": 100,
        "rule_type": "keyword",
        "match_pattern": "contains",
        "field_target": "description",
        "match_value": "",
        "category": "",
        "tags": "",
        "is_active": True,
        "notes": "",
        "filter_account": "",
        "filter_currency": "",
        "filter_date_from": "",
        "filter_date_to": "",
        "conditions": [],
    }


def prefill_rule_from_transaction(txn: Transaction) -> dict[str, Any]:
    """Return a rule form view-model pre-filled from ``txn``.

    Heuristics (first that applies):

    1. structured ``merchant_name`` / ``name`` / ``counterparty`` -> a
       ``structured_field`` rule keyed on that field.
    2. an IBAN (structured ``iban`` / ``payer_iban``) -> an ``account_iban`` rule.
    3. otherwise a ``keyword`` rule on the description.

    The originating account becomes ``filter_account`` so the rule is scoped by
    default; the effective category seeds ``category``.
    """
    vm = blank_rule_vm()
    vm["category"] = _first_category(txn)
    vm["filter_account"] = txn.accountNumber or ""
    vm["notes"] = f"Created from transaction: {(txn.description or 'N/A')[:120]}"

    structured = _parse_structured(txn)

    for field in _STRUCTURED_PRIORITY:
        value = structured.get(field)
        if value:
            vm["rule_type"] = "structured_field"
            vm["field_target"] = field
            vm["match_value"] = str(value)
            return vm

    iban = structured.get("iban") or structured.get("payer_iban")
    if iban:
        vm["rule_type"] = "account_iban"
        vm["field_target"] = "iban"
        vm["match_value"] = str(iban)
        return vm

    vm["rule_type"] = "keyword"
    vm["field_target"] = "description"
    vm["match_value"] = txn.description or ""
    return vm
