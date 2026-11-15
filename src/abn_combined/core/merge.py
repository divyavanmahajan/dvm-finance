"""The merge of the rows that report one payment.

The bank writes one SEPA payment in two description forms. The two forms hold a
different raw text, so the two forms give two different transaction ids. A
database from before the reference check can therefore hold one payment twice.
This module finds each such group and folds it to one row.

The merge keeps the row with the lowest id, writes ``deleted_at`` and
``merged_into`` on each other row, and stores a report. The merge deletes no
row, so the user can undo it. Only the purge deletes a row, and the purge keeps
each merged row.

The merge refuses a group whose rows hold two different manual categories. Only
the snapshot import may replace a manual categorization, so the merge does not
choose between the two values.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ..logging_config import get_logger
from .dedup import (
    counterparty_key,
    extract_end_to_end_reference,
    normalize_reference,
)
from .models import MergeReport, Transaction

logger = get_logger(__name__)


@dataclass
class MergeGroup:
    """One payment that the database holds more than one time."""

    account: str
    reference: str
    amount: str
    #: How the system found the group: ``reference`` or ``counterparty``.
    matched_by: str
    survivor_id: str
    merged_ids: list[str]
    carried_category: str | None = None
    carried_tags: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "reference": self.reference,
            "amount": self.amount,
            "matched_by": self.matched_by,
            "survivor_id": self.survivor_id,
            "merged_ids": list(self.merged_ids),
            "carried_category": self.carried_category,
            "carried_tags": self.carried_tags,
        }


@dataclass
class RefusedGroup:
    """One group that the merge refuses, with the reason."""

    account: str
    reference: str
    amount: str
    #: How the system found the group: ``reference`` or ``counterparty``.
    matched_by: str
    reason: str
    row_ids: list[str]
    manual_categories: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "reference": self.reference,
            "amount": self.amount,
            "matched_by": self.matched_by,
            "reason": self.reason,
            "row_ids": list(self.row_ids),
            "manual_categories": list(self.manual_categories),
        }


@dataclass
class MergePreview:
    """What a merge would do. The preview changes no row."""

    groups: list[MergeGroup] = field(default_factory=list)
    refused: list[RefusedGroup] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        """The number of rows that the merge would flag."""
        return sum(len(group.merged_ids) for group in self.groups)


_CONFLICTING_MANUAL_CATEGORY = "the rows hold two different manual categories"
_ONE_STATEMENT_FILE = (
    "one statement file gives more than one row of the group, so the group "
    "holds a repeated payment and not two forms of one payment"
)


def _amount_key(amount: Any) -> str:
    """Return the amount as a stable string with two decimal places."""
    if amount is None:
        return ""
    try:
        return f"{Decimal(str(amount)):.2f}"
    except (ArithmeticError, ValueError):
        return str(amount)


def _usable_reference(row: Transaction) -> str | None:
    """Return the reference of a stored row, or None when it names no payment.

    The function reads the column first, and otherwise the structured
    description. A row from before the backfill can hold the value in the
    structured description only.
    """
    if row.end_to_end_reference:
        return extract_end_to_end_reference(
            {"end_to_end_reference": row.end_to_end_reference}
        )
    return extract_end_to_end_reference(
        {"description_structured": row.description_structured}
    )


def _structured_of(row: Transaction) -> dict[str, Any]:
    """Return the stored structured description of a row, as a dictionary."""
    if not row.description_structured:
        return {}
    try:
        data = json.loads(row.description_structured)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _row_as_dict(row: Transaction) -> dict[str, Any]:
    """Return the fields of a stored row that a match key needs."""
    return {
        "accountNumber": row.accountNumber,
        "transactiondate": row.transactiondate,
        "amount": row.amount,
        "description_structured": row.description_structured,
        "end_to_end_reference": row.end_to_end_reference,
        "source_file": row.source_file,
    }


def _manual_categories(rows: list[Transaction]) -> list[str]:
    """Return each distinct manual category of a group, in a stable order."""
    values = {row.manual_category for row in rows if row.manual_category}
    return sorted(values)


def preview_merge(db: Session) -> MergePreview:
    """Find each group of duplicate rows, and say what a merge would do.

    The function changes no row. It reads each live row, groups the rows by the
    account and the reference, and keeps a group of two rows or more.
    """
    rows = (
        db.query(Transaction)
        .filter(Transaction.deleted_at.is_(None))
        .order_by(Transaction.id)
        .all()
    )

    # The key holds the amount as well as the account and the reference. A
    # reversal carries the reference of the payment that it reverses, with the
    # opposite sign. Those are two transactions, and the merge must not join
    # them. The two description forms of one payment always report the same
    # amount, because they describe one statement line.
    #
    # The key normalizes the reference, because the two forms can print one
    # reference with different separators.
    # ``groups`` maps a sort key to (how it matched, the rows). A row belongs to
    # one group only: the reference key wins, and the counterparty key covers
    # the rows that hold no usable reference.
    groups: dict[tuple[str, ...], tuple[str, list[Transaction]]] = {}

    for row in rows:
        reference = _usable_reference(row)
        if reference is not None:
            key = (
                "reference",
                str(row.accountNumber),
                normalize_reference(reference),
                _amount_key(row.amount),
            )
            groups.setdefault(key, ("reference", []))[1].append(row)
            continue

        # A transfer between two accounts of the user carries no reference. Only
        # the counterparty IBAN with the remittance text joins its two forms.
        #
        # Caution: use the whole key. It holds the transaction date, and without
        # the date each monthly transfer of one amount to one account joins one
        # group.
        other = counterparty_key(_row_as_dict(row))
        if other is None:
            continue
        groups.setdefault(("counterparty", *other), ("counterparty", []))[1].append(
            row
        )

    preview = MergePreview()

    for _key, (matched_by, members) in sorted(groups.items()):
        if len(members) < 2:
            continue

        # Read the account and the amount from a row, so that the two kinds of
        # key need no shared position.
        account = str(members[0].accountNumber)
        amount = _amount_key(members[0].amount)

        # Show the original text of the first row, so that the report and the
        # page name what the bank wrote.
        if matched_by == "reference":
            display_reference = _usable_reference(members[0]) or ""
        else:
            data = _structured_of(members[0])
            display_reference = str(data.get("iban") or "")
            remittance = str(data.get("remittance_info") or "")
            if remittance:
                display_reference = f"{display_reference} / {remittance}"

        # Two rows of one statement file are two payments. The bank changed the
        # description form between two downloads, so two forms of one payment
        # always come from two files.
        if matched_by == "counterparty":
            per_file: dict[str, int] = {}
            for row in members:
                name = str(row.source_file or "")
                per_file[name] = per_file.get(name, 0) + 1
            if max(per_file.values()) > 1:
                preview.refused.append(
                    RefusedGroup(
                        account=account,
                        reference=display_reference,
                        amount=amount,
                        matched_by=matched_by,
                        reason=_ONE_STATEMENT_FILE,
                        row_ids=[row.id for row in members],
                        manual_categories=_manual_categories(members),
                    )
                )
                continue

        categories = _manual_categories(members)
        if len(categories) > 1:
            preview.refused.append(
                RefusedGroup(
                    account=account,
                    reference=display_reference,
                    amount=amount,
                    matched_by=matched_by,
                    reason=_CONFLICTING_MANUAL_CATEGORY,
                    row_ids=[row.id for row in members],
                    manual_categories=categories,
                )
            )
            continue

        # The survivor is the lowest id in the lexicographic order. The choice
        # is stable, so two machines pick the same row with no sync. A choice by
        # the import order or by the source file could differ between two
        # machines, and the payment would then disappear from the merged
        # snapshot.
        ordered = sorted(members, key=lambda row: row.id)
        survivor, others = ordered[0], ordered[1:]

        carried_category = None
        carried_tags = None
        if not survivor.manual_category:
            for row in others:
                if row.manual_category:
                    carried_category = row.manual_category
                    break
        if not survivor.manual_tags:
            for row in others:
                if row.manual_tags:
                    carried_tags = row.manual_tags
                    break

        preview.groups.append(
            MergeGroup(
                account=account,
                reference=display_reference,
                amount=amount,
                matched_by=matched_by,
                survivor_id=survivor.id,
                merged_ids=[row.id for row in others],
                carried_category=carried_category,
                carried_tags=carried_tags,
            )
        )

    return preview


def merge_duplicates(db: Session, *, commit: bool = True) -> MergePreview:
    """Merge each group of duplicate rows, and return what the merge did.

    The function flags each row that is not the survivor, and it names the
    survivor in ``merged_into``. It carries the manual categorization to a
    survivor that holds none. It changes no row of a refused group. The
    function stores a report, so that the user can read what it did.
    """
    preview = preview_merge(db)
    if not preview.groups and not preview.refused:
        return preview

    now = datetime.now()

    for group in preview.groups:
        survivor = db.get(Transaction, group.survivor_id)
        if survivor is None:  # pragma: no cover - the preview just read it
            continue

        if group.carried_category:
            survivor.manual_category = group.carried_category
        if group.carried_tags:
            survivor.manual_tags = group.carried_tags
        if group.carried_category or group.carried_tags:
            survivor.updated_at = now

        for row_id in group.merged_ids:
            row = db.get(Transaction, row_id)
            if row is None:  # pragma: no cover
                continue
            row.deleted_at = now
            row.merged_into = group.survivor_id
            row.updated_at = now

    db.add(
        MergeReport(
            groups=[group.as_dict() for group in preview.groups],
            refused=[group.as_dict() for group in preview.refused],
            summary={
                "groups": len(preview.groups),
                "rows": preview.row_count,
                "refused": len(preview.refused),
            },
        )
    )

    if commit:
        db.commit()

    logger.info(
        "duplicates_merged",
        groups=len(preview.groups),
        rows=preview.row_count,
        refused=len(preview.refused),
    )
    return preview


def undo_merge(db: Session, survivor_id: str, *, commit: bool = True) -> list[str]:
    """Undo one merge, and return the id of each row that comes back.

    The function clears ``deleted_at`` and ``merged_into`` on each row that
    names the survivor. It keeps each manual categorization that the merge
    carried to the survivor, because the user may have relied on it since.
    """
    rows = (
        db.query(Transaction).filter(Transaction.merged_into == survivor_id).all()
    )

    restored: list[str] = []
    now = datetime.now()
    for row in rows:
        row.deleted_at = None
        row.merged_into = None
        row.updated_at = now
        restored.append(row.id)

    if commit:
        db.commit()

    logger.info("merge_undone", survivor=survivor_id, restored=len(restored))
    return restored
