"""One-time rewrite of the stored structured description of a SEPA row.

The rules read ``description_structured``, and not the raw text. A rename of a
key in the parser therefore changes nothing for a row that the system already
stored. This module reparses each stored SEPA description with the present
parser, so that a rule on a canonical key matches a row from before the change.

The pass is self-limiting. :func:`needs_rewrite` names only a row that still
holds an old key or the old format value. After the first run no row matches,
so a later startup writes nothing.

The word self-limiting describes the writes, and not the read: the pass loads
each row that holds a structured description on every startup. The single-user
database holds a few thousand rows, so the scan costs little. Give the pass a
marker if the row count grows.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..logging_config import get_logger
from ..parsers.description import parse_transaction_description
from .models import Transaction

logger = get_logger(__name__)

# The two key names that the labelled parser used before the change.
_OLD_KEYS = ("description", "reference")


def needs_rewrite(data: dict[str, Any]) -> bool:
    """Return True if a stored structured description holds an old shape.

    A row needs the rewrite when one of three tests holds:

    - It holds the format ``sepa`` with one of the two old key names.
    - It holds the format ``mt940`` with a transaction type that starts with
      ``SEPA``. A tagged SEPA row carried that format before the change.
    - It hides ``CSID`` or ``MARF`` inside ``other_fields``.
    """
    fmt = data.get("format")

    if fmt == "sepa" and any(key in data for key in _OLD_KEYS):
        return True

    if fmt == "mt940":
        transaction_type = data.get("transaction_type")
        if isinstance(transaction_type, str) and transaction_type.upper().startswith(
            "SEPA"
        ):
            return True

    other = data.get("other_fields")
    if isinstance(other, dict) and ("CSID" in other or "MARF" in other):
        return True

    return False


def rewrite_sepa_structured_descriptions(
    db: Session, *, commit: bool = True
) -> int:
    """Rewrite each stored SEPA structured description, and return the count.

    The function reparses the raw description. It writes the new value only when
    the parser returns one, so that a row with an unparseable description keeps
    what it holds. The function does not touch the category, the tags, or any
    manual field, so it changes no categorization.
    """
    rows = (
        db.query(Transaction)
        .filter(Transaction.description_structured.isnot(None))
        .all()
    )

    rewritten = 0
    for row in rows:
        try:
            data = json.loads(row.description_structured)
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict) or not needs_rewrite(data):
            continue

        parsed = parse_transaction_description(row.description or "")
        if not parsed:
            continue

        row.description_structured = json.dumps(parsed, ensure_ascii=False)
        reference = parsed.get("end_to_end_reference")
        if isinstance(reference, str) and reference.strip():
            row.end_to_end_reference = reference.strip()
        rewritten += 1

    if commit:
        db.commit()

    if rewritten:
        logger.info("sepa_structured_rewritten", count=rewritten)
    return rewritten


# ---------------------------------------------------------------------------
# The field target of a rule
# ---------------------------------------------------------------------------

# A rule names a structured key by its field target. An unknown field target
# matches nothing, so a rename of a key must carry each rule with it.
_RENAMES = {"reference": "end_to_end_reference"}

# The raw description keeps the field target `description`. Both match functions
# short-circuit that target to the raw text, whatever the rule type. Only a rule
# of the type `structured_field` reads the structured key of that name, so only
# such a rule takes this rename. An extra condition never takes it.
_STRUCTURED_RENAMES = {"description": "remittance_info"}

_STRUCTURED_RULE_TYPE = "structured_field"


def _new_target(field_target: str | None, rule_type: str | None) -> str | None:
    """Return the new field target, or None when the old one stays."""
    if not field_target:
        return None
    if field_target in _RENAMES:
        return _RENAMES[field_target]
    if rule_type == _STRUCTURED_RULE_TYPE and field_target in _STRUCTURED_RENAMES:
        return _STRUCTURED_RENAMES[field_target]
    return None


def migrate_rule_field_targets(db: Session, *, commit: bool = True):
    """Rename the field target of each rule that names a renamed key.

    The function returns the stored :class:`RuleChangeReport`, or None when no
    rule needs the rename. The report names each rule that the function changed
    and each transaction whose category or tags changed, so that the migration
    makes no silent recategorization.

    The function is idempotent. After the first run no rule names an old key.
    """
    from .categorizer import record_rule_change
    from .models import CategorizationRule, RuleCondition

    changed_rules: list[dict[str, Any]] = []

    for rule in db.query(CategorizationRule).all():
        new_target = _new_target(rule.field_target, rule.rule_type)
        if new_target is None:
            continue
        changed_rules.append(
            {
                "kind": "rule",
                "uuid": rule.uuid,
                "rule_id": rule.id,
                "rule_type": rule.rule_type,
                "from": rule.field_target,
                "to": new_target,
            }
        )
        rule.field_target = new_target

    # An extra condition takes the reference rename only. Its match function
    # reads the raw text for the target `description`, for each rule type.
    for condition in db.query(RuleCondition).all():
        if condition.field_target not in _RENAMES:
            continue
        new_target = _RENAMES[condition.field_target]
        changed_rules.append(
            {
                "kind": "condition",
                "condition_id": condition.id,
                "rule_id": condition.rule_id,
                "from": condition.field_target,
                "to": new_target,
            }
        )
        condition.field_target = new_target

    if not changed_rules:
        return None

    db.flush()
    logger.info("rule_field_targets_migrated", count=len(changed_rules))

    if not commit:
        return None

    # The report reapplies each rule and records every affected transaction. A
    # manual categorization does not change, because apply_rules skips a
    # manually categorized row.
    return record_rule_change(
        db,
        "migrate_fields",
        before={"renamed": [dict(c, to=c["from"]) for c in changed_rules]},
        after={"renamed": changed_rules},
    )
