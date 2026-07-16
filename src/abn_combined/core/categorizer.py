"""Rule-based categorization engine, preview, and change reports.

Ported from abn-analyst ``app/analyzer.py`` (rule-based part only — no LLM). Adds a
dry-run ``preview_rule`` and audit ``record_rule_change`` per spec FR4.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .models import (
    CategorizationRule,
    RuleChangeItem,
    RuleChangeReport,
    Transaction,
)
from .utils import normalize_string_for_matching

MANUAL_SOURCE = "manual"


class RuleValidationError(ValueError):
    """Raised when a rule (or condition) has an invalid regex pattern."""


# ---------------------------------------------------------------------------
# Regex validation (at construction time, never at match time)
# ---------------------------------------------------------------------------

def validate_rule_regex(rule: Any) -> None:
    """Validate every regex pattern on a rule and its conditions.

    Raises :class:`RuleValidationError` on the first invalid pattern.
    """
    def _check(pattern: str | None, value: str | None, where: str) -> None:
        if pattern == "regex":
            try:
                re.compile(value or "")
            except re.error as exc:
                raise RuleValidationError(f"Invalid regex in {where}: {exc}") from exc

    _check(getattr(rule, "match_pattern", None), getattr(rule, "match_value", None), "rule")
    for i, cond in enumerate(getattr(rule, "conditions", None) or []):
        _check(
            getattr(cond, "match_pattern", None),
            getattr(cond, "match_value", None),
            f"condition[{i}]",
        )


# ---------------------------------------------------------------------------
# Matching (ported)
# ---------------------------------------------------------------------------

def _parse_structured_data(trans: dict[str, Any]) -> dict | None:
    structured_desc = trans.get("description_structured")
    if not structured_desc:
        return None
    try:
        if isinstance(structured_desc, str):
            return json.loads(structured_desc)
        return structured_desc
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None


def _apply_match_pattern(field_value: str, match_pattern: str, match_value: str) -> bool:
    fv = normalize_string_for_matching(field_value)
    mv = normalize_string_for_matching(match_value)
    if match_pattern == "contains":
        return mv in fv
    elif match_pattern == "exact":
        return fv == mv
    elif match_pattern == "starts_with":
        return fv.startswith(mv)
    elif match_pattern == "ends_with":
        return fv.endswith(mv)
    elif match_pattern == "regex":
        try:
            return bool(re.search(match_value, fv, re.IGNORECASE))
        except re.error:
            return False
    return False


def _evaluate_single_condition(
    field_target: str,
    match_pattern: str,
    match_value: str,
    trans: dict[str, Any],
    structured_data: dict | None,
) -> bool:
    if field_target == "description":
        field_value = trans.get("description", "")
    elif field_target and structured_data:
        raw = structured_data.get(field_target, "")
        if raw is True:
            raw = "true"
        elif raw is False:
            raw = "false"
        field_value = str(raw) if raw is not None else ""
    else:
        return False
    return _apply_match_pattern(field_value, match_pattern, match_value)


def _check_primary_condition(
    rule: Any, trans: dict[str, Any], structured_data: dict | None
) -> bool:
    if rule.rule_type == "structured_field":
        if not structured_data:
            return False
        field_value = structured_data.get(rule.field_target, "")
        if field_value is True:
            field_value = "true"
        elif field_value is False:
            field_value = "false"
        return _apply_match_pattern(field_value, rule.match_pattern, rule.match_value)

    if rule.rule_type == "account_iban":
        if rule.field_target == "iban":
            iban = None
            if structured_data:
                iban = structured_data.get("iban")
            if not iban:
                desc_upper = trans.get("description", "").upper()
                m = re.search(r"IBAN[:\s]+([A-Z]{2}\d{2}[A-Z0-9]{4,30})", desc_upper)
                if m:
                    iban = m.group(1)
            if iban:
                iban_norm = normalize_string_for_matching(iban)
                mv_norm = normalize_string_for_matching(rule.match_value)
                if rule.match_pattern == "exact":
                    return iban_norm == mv_norm
                elif rule.match_pattern == "ends_with":
                    return iban_norm.endswith(mv_norm)
                elif rule.match_pattern == "contains":
                    return mv_norm in iban_norm
        elif rule.field_target == "description":
            desc_norm = normalize_string_for_matching(trans.get("description", ""))
            mv_norm = normalize_string_for_matching(rule.match_value)
            return mv_norm in desc_norm
        return False

    if rule.field_target == "description" or rule.rule_type == "full_description":
        field_value = trans.get("description", "")
    elif rule.field_target and structured_data:
        raw = structured_data.get(rule.field_target, "")
        if raw is True:
            raw = "true"
        elif raw is False:
            raw = "false"
        field_value = str(raw) if raw is not None else ""
    else:
        return False

    return _apply_match_pattern(field_value, rule.match_pattern, rule.match_value)


def _apply_rule_to_transaction(rule: Any, trans: dict[str, Any]) -> bool:
    """Return True if a rule's primary condition, extra conditions and filters match."""
    structured_data = _parse_structured_data(trans)

    if not _check_primary_condition(rule, trans, structured_data):
        return False

    conditions = getattr(rule, "conditions", None)
    if conditions:
        running = True
        for cond in conditions:
            result = _evaluate_single_condition(
                cond.field_target,
                cond.match_pattern,
                cond.match_value,
                trans,
                structured_data,
            )
            if cond.operator == "OR":
                running = running or result
            else:
                running = running and result
        if not running:
            return False

    if getattr(rule, "filter_account", None):
        if trans.get("accountNumber") != rule.filter_account:
            return False
    if getattr(rule, "filter_currency", None):
        if trans.get("currency") != rule.filter_currency:
            return False
    filter_date_from = getattr(rule, "filter_date_from", None)
    filter_date_to = getattr(rule, "filter_date_to", None)
    if filter_date_from or filter_date_to:
        trans_date = trans.get("transactiondate")
        if trans_date:
            if isinstance(trans_date, str):
                try:
                    trans_date = date_type.fromisoformat(trans_date)
                except ValueError:
                    trans_date = None
            if trans_date:
                if filter_date_from and trans_date < filter_date_from:
                    return False
                if filter_date_to and trans_date > filter_date_to:
                    return False

    return True


# ---------------------------------------------------------------------------
# Transaction <-> dict helpers
# ---------------------------------------------------------------------------

def _txn_to_dict(txn: Transaction) -> dict[str, Any]:
    return {
        "description": txn.description or "",
        "description_structured": txn.description_structured,
        "accountNumber": txn.accountNumber,
        "currency": txn.currency,
        "transactiondate": txn.transactiondate,
    }


def _rule_result(rule: Any) -> tuple[str, str | None]:
    """Return the (category, tags) a matching rule would assign."""
    category = (rule.category or "").lower() if rule.category else None
    tags = rule.tags if getattr(rule, "tags", None) else None
    return category, tags


def _first_match(rules: list[Any], trans: dict[str, Any]) -> Any | None:
    for rule in rules:
        if _apply_rule_to_transaction(rule, trans):
            return rule
    return None


def _load_active_rules(db: Session) -> list[CategorizationRule]:
    return (
        db.query(CategorizationRule)
        .filter(CategorizationRule.is_active.is_(True))
        .order_by(CategorizationRule.priority.asc(), CategorizationRule.id.asc())
        .all()
    )


def _split_rules(
    rules: list[Any],
) -> tuple[list[Any], list[Any]]:
    """Split rules into (category_rules, tag_only_rules), each in priority order."""
    category_rules = [r for r in rules if not getattr(r, "is_tag_only", False)]
    tag_only_rules = [r for r in rules if getattr(r, "is_tag_only", False)]
    return category_rules, tag_only_rules


def _merge_tags(existing_tags: str | None, new_tags: str | None) -> str | None:
    """Merge tag strings, de-duplicating while preserving first-seen order."""
    if not new_tags:
        return existing_tags
    existing_list = [t.strip() for t in (existing_tags or "").split(",") if t.strip()]
    new_list = [t.strip() for t in new_tags.split(",") if t.strip()]
    merged: list[str] = list(existing_list)
    for t in new_list:
        if t not in merged:
            merged.append(t)
    return ",".join(merged) if merged else None


def _is_manual(txn: Transaction) -> bool:
    return txn.categorization_source == MANUAL_SOURCE


def _is_transfer(txn: Transaction) -> bool:
    """Check if transaction is categorized as a transfer (case-insensitive)."""
    eff_category = txn.manual_category if txn.manual_category else txn.category
    return eff_category and "transfer" in eff_category.lower()


# ---------------------------------------------------------------------------
# apply_rules
# ---------------------------------------------------------------------------

@dataclass
class TxnChange:
    transaction_id: str
    old_category: str | None
    new_category: str | None
    old_tags: str | None
    new_tags: str | None


def apply_rules(
    db: Session,
    transaction_ids: list[str] | None = None,
    rules: list[CategorizationRule] | None = None,
    commit: bool = True,
) -> list[TxnChange]:
    """Reapply active rules to transactions.

    Two-pass application:

    1. Category rules (``is_tag_only=False``) are applied in priority order, first
       match wins, to non-manual transactions only. Writes ``category``, ``tags``
       and ``categorization_source`` (str(rule.id)); a transaction with no matching
       category rule gets ``category=None`` (effective "Uncategorized"). Never
       touches ``manual_category``/``manual_tags`` and skips transactions whose
       ``categorization_source == "manual"``.
    2. Tag-only rules (``is_tag_only=True``) are then applied *regardless of
       priority* — every matching tag-only rule contributes its tags, merged
       (de-duplicated) onto whatever tags are already present. Tag-only rules run
       against **all** transactions, including manually categorized ones, and never
       change ``category``/``manual_category``.

    Returns the list of transactions whose rule-assigned category or tags changed.
    """
    if rules is None:
        rules = _load_active_rules(db)
    category_rules, tag_only_rules = _split_rules(rules)

    query = db.query(Transaction)
    if transaction_ids is not None:
        query = query.filter(Transaction.id.in_(transaction_ids))
    txns = query.all()

    changes: dict[str, TxnChange] = {}

    # Pass 1: category rules, non-manual transactions only, first match wins.
    for txn in txns:
        if _is_manual(txn):
            continue

        old_category = txn.category
        old_tags = txn.tags

        rule = _first_match(category_rules, _txn_to_dict(txn))
        if rule is None:
            new_category, new_tags, new_source = None, None, None
        else:
            new_category, new_tags = _rule_result(rule)
            new_source = str(rule.id)

        if new_category != old_category or new_tags != old_tags:
            txn.category = new_category
            txn.tags = new_tags
            txn.categorization_source = new_source
            txn.updated_at = datetime.now()
            changes[txn.id] = TxnChange(
                txn.id, old_category, new_category, old_tags, new_tags
            )
        else:
            # Keep categorization_source in sync even when category is unchanged.
            txn.categorization_source = new_source

    # Pass 2: tag-only rules, all matching transactions (including manual ones),
    # every match applies (not just the first). Category is never touched.
    for txn in txns:
        trans = _txn_to_dict(txn)
        pre_tags = txn.tags
        merged_tags = txn.tags
        for rule in tag_only_rules:
            if _apply_rule_to_transaction(rule, trans):
                merged_tags = _merge_tags(merged_tags, rule.tags)

        if merged_tags != pre_tags:
            existing = changes.get(txn.id)
            if existing is not None:
                existing.new_tags = merged_tags
            else:
                changes[txn.id] = TxnChange(
                    txn.id, txn.category, txn.category, pre_tags, merged_tags
                )
            txn.tags = merged_tags
            txn.updated_at = datetime.now()

    if commit:
        db.commit()
    return list(changes.values())


# ---------------------------------------------------------------------------
# preview_rule (dry-run, no writes)
# ---------------------------------------------------------------------------

@dataclass
class PreviewResult:
    matched: list[str] = field(default_factory=list)
    gains: list[str] = field(default_factory=list)
    losses: list[str] = field(default_factory=list)
    changes: list[TxnChange] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "gains": self.gains,
            "losses": self.losses,
            "changes": [c.__dict__ for c in self.changes],
            "counts": {
                "matched": len(self.matched),
                "gains": len(self.gains),
                "losses": len(self.losses),
                "changes": len(self.changes),
            },
        }


def preview_rule(
    db: Session,
    draft_rule: Any,
    existing_rule_id: int | None = None,
    include_transfers: bool = False,
) -> PreviewResult:
    """Dry-run a draft rule and report matches + the diff vs current state.

    Args:
        db: Database session
        draft_rule: The draft rule to preview
        existing_rule_id: ID of rule being edited (if any)
        include_transfers: If False (default), exclude transfer transactions

    Returns:
        PreviewResult with:
        - ``matched``: non-manual transactions the draft rule matches.
        - ``gains``: transactions newly attributed to this rule (not previously so).
        - ``losses``: transactions the *old* version of this rule categorized that the
          draft no longer matches.
        - ``changes``: per-transaction category/tag changes the draft would cause,
          simulated against the full active rule set with the draft substituted in.
    """
    validate_rule_regex(draft_rule)

    active = _load_active_rules(db)

    # Build the simulated rule set: substitute the draft for the edited rule, or
    # append it (respecting priority ordering) for a new rule.
    simulated = [r for r in active if r.id != existing_rule_id]
    simulated.append(draft_rule)
    simulated.sort(key=lambda r: (getattr(r, "priority", 100), getattr(r, "id", 0) or 0))

    result = PreviewResult()
    old_attributed = set()
    if existing_rule_id is not None:
        old_source = str(existing_rule_id)
        old_attributed = {
            t.id
            for t in db.query(Transaction.id, Transaction.categorization_source)
            if t.categorization_source == old_source
        }

    for txn in db.query(Transaction).all():
        if _is_manual(txn):
            continue
        # Skip transfers unless include_transfers is True
        if not include_transfers and _is_transfer(txn):
            continue
        trans = _txn_to_dict(txn)

        draft_matches = _apply_rule_to_transaction(draft_rule, trans)
        if draft_matches:
            result.matched.append(txn.id)

        winner = _first_match(simulated, trans)
        winner_is_draft = winner is draft_rule
        if winner_is_draft and txn.id not in old_attributed:
            result.gains.append(txn.id)

        if existing_rule_id is not None and txn.id in old_attributed and not draft_matches:
            result.losses.append(txn.id)

        # Category/tag change vs current stored state.
        if winner is None:
            new_category, new_tags = None, None
        else:
            new_category, new_tags = _rule_result(winner)
        if new_category != txn.category or new_tags != txn.tags:
            result.changes.append(
                TxnChange(txn.id, txn.category, new_category, txn.tags, new_tags)
            )

    return result


# ---------------------------------------------------------------------------
# Rule snapshots + change reports
# ---------------------------------------------------------------------------

def rule_snapshot(rule: CategorizationRule | None) -> dict[str, Any] | None:
    """Serialise a rule (and its conditions) to a JSON-safe snapshot dict."""
    if rule is None:
        return None
    return {
        "id": rule.id,
        "uuid": rule.uuid,
        "priority": rule.priority,
        "rule_type": rule.rule_type,
        "match_pattern": rule.match_pattern,
        "field_target": rule.field_target,
        "match_value": rule.match_value,
        "category": rule.category,
        "tags": rule.tags,
        "is_active": rule.is_active,
        "is_tag_only": rule.is_tag_only,
        "notes": rule.notes,
        "filter_account": rule.filter_account,
        "filter_currency": rule.filter_currency,
        "filter_date_from": rule.filter_date_from.isoformat() if rule.filter_date_from else None,
        "filter_date_to": rule.filter_date_to.isoformat() if rule.filter_date_to else None,
        "conditions": [
            {
                "field_target": c.field_target,
                "match_pattern": c.match_pattern,
                "match_value": c.match_value,
                "operator": c.operator,
                "sort_order": c.sort_order,
            }
            for c in (rule.conditions or [])
        ],
    }


def record_rule_change(
    db: Session,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    rule_id: int | None = None,
    rule_uuid: str | None = None,
) -> RuleChangeReport:
    """Reapply all rules to non-manual transactions and persist an audit report.

    Used by create/update/delete/toggle and by "recategorize all" (action=
    ``recategorize``). Returns the stored :class:`RuleChangeReport`.
    """
    changes = apply_rules(db, commit=False)

    if rule_id is None and after:
        rule_id = after.get("id")
    if rule_uuid is None:
        rule_uuid = (after or before or {}).get("uuid")

    report = RuleChangeReport(
        action=action,
        rule_id=rule_id,
        rule_uuid=rule_uuid,
        rule_before=before,
        rule_after=after,
        summary={"changed": len(changes)},
    )
    for ch in changes:
        report.items.append(
            RuleChangeItem(
                transaction_id=ch.transaction_id,
                old_category=ch.old_category,
                new_category=ch.new_category,
                old_tags=ch.old_tags,
                new_tags=ch.new_tags,
            )
        )
    db.add(report)
    db.commit()
    return report
