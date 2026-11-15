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
        "is_tag_only": False,
        "notes": "",
        "filter_account": "",
        "filter_currency": "",
        "filter_date_from": "",
        "filter_date_to": "",
        "conditions": [],
        # Field list (rule-editor-field-checklist). Empty without a sample.
        "field_rows": [],
        "sample_transaction_id": None,
        "sample_account": "",
        "sample_currency": "",
    }


def _heuristic_match(txn: Transaction) -> tuple[str, str, str]:
    """Return ``(rule_type, field_target, match_value)`` for ``txn``.

    Heuristics (first that applies):

    1. structured ``merchant_name`` / ``name`` / ``counterparty`` -> a
       ``structured_field`` rule keyed on that field.
    2. an IBAN (structured ``iban`` / ``payer_iban``) -> an ``account_iban`` rule.
    3. otherwise a ``keyword`` rule on the description.
    """
    structured = _parse_structured(txn)
    for field in _STRUCTURED_PRIORITY:
        value = structured.get(field)
        if value:
            return "structured_field", field, str(value)
    iban = structured.get("iban") or structured.get("payer_iban")
    if iban:
        return "account_iban", "iban", str(iban)
    return "keyword", "description", txn.description or ""


# Field-list order: these structured fields first, then the other structured
# fields in their stored order, then the description.
_FIELD_ORDER = ("merchant_name", "name", "counterparty", "iban")


def _field_text(value: Any) -> str | None:
    """Return the text the matcher compares for a structured value, or None."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value)
    return text or None


def _sample_fields(txn: Transaction) -> list[tuple[str, str]]:
    structured = _parse_structured(txn)
    texts = {k: _field_text(v) for k, v in structured.items()}
    ordered = [k for k in _FIELD_ORDER if k in texts]
    ordered += [k for k in texts if k not in _FIELD_ORDER and k != "description"]
    fields = [(k, texts[k]) for k in ordered if texts[k]]
    fields.append(("description", txn.description or ""))
    return fields


def build_field_rows(
    txn: Transaction, vm: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(rows, advanced_conditions)`` for the field list of ``txn``.

    Each row holds ``field``, ``value``, ``pattern``, ``selected`` and
    ``in_sample``. The primary match of ``vm`` and its conditions up to the
    first ``OR`` become selected rows with their own pattern and value. A
    second condition on a field that is already selected, and each condition
    from the first ``OR``, go back as advanced conditions. A draft field that
    the sample does not hold becomes an extra selected row.
    """
    rows = [
        {"field": f, "value": v, "pattern": "contains", "selected": False, "in_sample": True}
        for f, v in _sample_fields(txn)
    ]
    by_field = {r["field"]: r for r in rows}

    def select(field: str, pattern: str, value: str) -> None:
        row = by_field.get(field)
        if row is None:
            row = {"field": field, "value": value, "pattern": pattern,
                   "selected": True, "in_sample": False}
            rows.append(row)
            by_field[field] = row
        row.update(value=value, pattern=pattern or "contains", selected=True)

    if vm.get("match_value"):
        primary = vm.get("field_target") or "description"
        if vm.get("rule_type") == "full_description":
            primary = "description"
        select(primary, vm.get("match_pattern") or "contains", vm["match_value"])

    advanced: list[dict[str, Any]] = []
    leading = True
    for cond in vm.get("conditions") or []:
        if cond.get("operator", "AND") != "AND":
            leading = False
        field = cond.get("field_target") or ""
        row = by_field.get(field)
        if leading and field and not (row and row["selected"]):
            select(field, cond.get("match_pattern") or "contains", cond.get("match_value") or "")
        else:
            advanced.append(dict(cond))
    return rows, advanced


def apply_sample(vm: dict[str, Any], txn: Transaction) -> dict[str, Any]:
    """Return a copy of ``vm`` with the field list of the sample ``txn``.

    The rest of the draft (category, tags, filters, ...) stays as it is. A
    draft with no match value gets the heuristic row selected.
    """
    out = dict(vm)
    if not out.get("match_value"):
        out["rule_type"], out["field_target"], out["match_value"] = _heuristic_match(txn)
        out["match_pattern"] = "contains"
    rows, advanced = build_field_rows(txn, out)
    out["field_rows"] = rows
    out["conditions"] = advanced
    out["sample_transaction_id"] = txn.id
    out["sample_account"] = txn.accountNumber or ""
    out["sample_currency"] = txn.currency or ""
    return out


def prefill_rule_from_transaction(txn: Transaction) -> dict[str, Any]:
    """Return a rule form view-model pre-filled from ``txn``.

    The match comes from :func:`_heuristic_match`, and ``txn`` becomes the
    sample of the field list with that row selected. The originating account
    becomes ``filter_account`` so the rule is scoped by default; the effective
    category seeds ``category``.
    """
    vm = blank_rule_vm()
    vm["category"] = _first_category(txn)
    vm["filter_account"] = txn.accountNumber or ""
    vm["notes"] = f"Created from transaction: {(txn.description or 'N/A')[:120]}"
    vm["rule_type"], vm["field_target"], vm["match_value"] = _heuristic_match(txn)
    return apply_sample(vm, txn)
