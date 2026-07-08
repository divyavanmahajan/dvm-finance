"""Rename/delete propagation for tags and categories across all tables.

Ported from abn-analyst ``scripts/rename_category_or_tag.py``. A rename touches:

- tags:       ``transactions.tags``, ``transactions.manual_tags``, ``rules.tags``
- categories: ``transactions.category``, ``transactions.manual_category``,
              ``rules.category``, ``budgets.category``

Manual values are renamed in lockstep with rule-assigned values, so manual
precedence semantics are untouched (Golden Principle 2: the *columns* keep their
meaning; only the label changes).

Audit semantics (Golden Principle 5): when a rename modifies a rule, a
:class:`RuleChangeReport` (action ``update``) is stored per affected rule with
before/after snapshots. No rule reapplication happens — transactions are renamed
in the same commit, so there is nothing to recategorize and reapplying rules here
would cause unrelated churn.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..logging_config import get_logger
from .categorizer import rule_snapshot
from .models import Budget, CategorizationRule, RuleChangeReport, Transaction
from .utils import normalize_category

logger = get_logger(__name__)


def _replace_in_comma_separated(value: str | None, old_val: str, new_val: str) -> str | None:
    """Replace ``old_val`` with ``new_val`` in a comma-separated string.

    Exact match per part, case-insensitive. Returns the original value when
    nothing matched (so callers can compare identity/equality for change checks).
    """
    if not value or not value.strip():
        return value
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        return value
    old_norm = old_val.strip().lower()
    updated = []
    changed = False
    for p in parts:
        if p.lower() == old_norm:
            updated.append(new_val.strip())
            changed = True
        else:
            updated.append(p)
    return ", ".join(updated) if changed else value


def _remove_from_comma_separated(value: str | None, name: str) -> str | None:
    """Remove ``name`` from a comma-separated string (case-insensitive exact part).

    Returns ``None`` when the last part is removed, or the original value when
    nothing matched.
    """
    if not value or not value.strip():
        return value
    parts = [p.strip() for p in value.split(",") if p.strip()]
    target = name.strip().lower()
    kept = [p for p in parts if p.lower() != target]
    if len(kept) == len(parts):
        return value
    return ", ".join(kept) if kept else None


def _audit_rule_change(db: Session, rule: CategorizationRule, before: dict,
                       summary: dict) -> None:
    db.add(
        RuleChangeReport(
            action="update",
            rule_id=rule.id,
            rule_uuid=rule.uuid,
            rule_before=before,
            rule_after=rule_snapshot(rule),
            summary=summary,
        )
    )


def rename_tag(db: Session, old_value: str, new_value: str) -> dict:
    """Rename a tag everywhere: both transaction tag columns and rules.tags."""
    old_val = old_value.strip()
    new_val = new_value.strip()
    if not new_val:
        return {"error": "New tag value cannot be empty"}

    stats = {"transactions_tags": 0, "transactions_manual_tags": 0, "rules_tags": 0}

    for txn in db.query(Transaction).filter(Transaction.tags.isnot(None)).all():
        new_tags = _replace_in_comma_separated(txn.tags, old_val, new_val)
        if new_tags != txn.tags:
            txn.tags = new_tags
            stats["transactions_tags"] += 1

    for txn in db.query(Transaction).filter(Transaction.manual_tags.isnot(None)).all():
        new_tags = _replace_in_comma_separated(txn.manual_tags, old_val, new_val)
        if new_tags != txn.manual_tags:
            txn.manual_tags = new_tags
            stats["transactions_manual_tags"] += 1

    for rule in (
        db.query(CategorizationRule).filter(CategorizationRule.tags.isnot(None)).all()
    ):
        new_tags = _replace_in_comma_separated(rule.tags, old_val, new_val)
        if new_tags != rule.tags:
            before = rule_snapshot(rule)
            rule.tags = new_tags
            _audit_rule_change(
                db, rule, before,
                {"rename": "tag", "old": old_val, "new": new_val},
            )
            stats["rules_tags"] += 1

    db.commit()
    logger.info("tag_renamed", old=old_val, new=new_val, **stats)
    return stats


def rename_category(db: Session, old_value: str, new_value: str) -> dict:
    """Rename a category everywhere: transactions (both columns), rules, budgets."""
    old_val = old_value.strip()
    new_val = normalize_category(new_value) or new_value.strip()
    if not new_val:
        return {"error": "New category value cannot be empty"}

    stats = {
        "transactions_category": 0,
        "transactions_manual_category": 0,
        "rules_category": 0,
        "budgets_category": 0,
    }

    for txn in db.query(Transaction).filter(Transaction.category.isnot(None)).all():
        new_cat = _replace_in_comma_separated(txn.category, old_val, new_val)
        if new_cat != txn.category:
            txn.category = new_cat
            stats["transactions_category"] += 1

    for txn in (
        db.query(Transaction).filter(Transaction.manual_category.isnot(None)).all()
    ):
        new_cat = _replace_in_comma_separated(txn.manual_category, old_val, new_val)
        if new_cat != txn.manual_category:
            txn.manual_category = new_cat
            stats["transactions_manual_category"] += 1

    for rule in db.query(CategorizationRule).all():
        if rule.category and rule.category.strip().lower() == old_val.lower():
            before = rule_snapshot(rule)
            rule.category = new_val
            _audit_rule_change(
                db, rule, before,
                {"rename": "category", "old": old_val, "new": new_val},
            )
            stats["rules_category"] += 1

    for budget in db.query(Budget).all():
        if budget.category and budget.category.strip().lower() == old_val.lower():
            budget.category = new_val
            stats["budgets_category"] += 1

    db.commit()
    logger.info("category_renamed", old=old_val, new=new_val, **stats)
    return stats


def delete_tag(db: Session, name: str) -> dict:
    """Remove a tag from both transaction tag columns (legacy semantics).

    Rule-assigned ``rules.tags`` are intentionally left alone (as in abn-analyst):
    deleting the tag from transactions is a data cleanup; editing a rule is a
    separate, audited action on the Rules page.
    """
    stats = {"transactions": 0}
    for txn in (
        db.query(Transaction)
        .filter((Transaction.tags.isnot(None)) | (Transaction.manual_tags.isnot(None)))
        .all()
    ):
        changed = False
        new_tags = _remove_from_comma_separated(txn.tags, name)
        if new_tags != txn.tags:
            txn.tags = new_tags
            changed = True
        new_manual = _remove_from_comma_separated(txn.manual_tags, name)
        if new_manual != txn.manual_tags:
            txn.manual_tags = new_manual
            changed = True
        if changed:
            stats["transactions"] += 1
    db.commit()
    logger.info("tag_deleted", name=name, **stats)
    return stats
