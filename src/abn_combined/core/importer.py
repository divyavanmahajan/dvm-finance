"""Unified import pipeline: parse -> dedup -> insert -> apply rules -> summary."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..logging_config import get_logger
from ..parsers import (
    parse_csv_file,
    parse_ftfcu_file,
    parse_paypal_file,
    parse_seb_file,
    parse_statement_file,
    parse_wise_file,
)
from .categorizer import apply_rules
from .dedup import (
    DEFAULT_CURRENCY,
    ReservedAccountError,
    check_duplicates,
    generate_transaction_id,
    insert_transactions,
    reject_reserved_account,
)
from .models import Transaction
from .utils import calculate_transaction_hash_components

logger = get_logger(__name__)

# Explicit format overrides (auto = detect by extension, and by the SEB header
# row for a .csv file, via parse_statement_file).
VALID_FORMATS = ("auto", "paypal", "wise", "seb", "ftfcu", "csv")


class ImportError_(ValueError):
    """Raised when a file cannot be parsed into any transactions."""


@dataclass
class ImportSummary:
    source_file: str
    new: int = 0
    duplicates: int = 0
    categorized: int = 0
    uncategorized: int = 0
    corrected: int = 0
    new_ids: list[str] = field(default_factory=list)
    # One dict for each corrected row: ``id``, ``old_amount``, ``new_amount``.
    corrections: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _store_file(content: bytes, filename: str, statements_dir: Path) -> Path:
    """Persist the uploaded bytes under ``statements/`` with a collision-proof name."""
    statements_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name or "upload.dat"
    dest = statements_dir / f"{uuid.uuid4().hex}_{safe_name}"
    dest.write_bytes(content)
    return dest


def _parse(path: Path, fmt: str, db: Session) -> list[dict]:
    if fmt == "paypal":
        return parse_paypal_file(path)
    if fmt == "wise":
        return parse_wise_file(path, db)
    if fmt == "seb":
        return parse_seb_file(path)
    if fmt == "ftfcu":
        return parse_ftfcu_file(path)
    if fmt == "csv":
        return parse_csv_file(path)
    return parse_statement_file(path)


def correct_amounts(db: Session, duplicates: list[dict]) -> list[dict[str, Any]]:
    """Correct the stored amount of each duplicate that has the same id.

    A provider id (PayPal, Wise, SEB) does not hold the amount, so a fixed
    parser gives a stored row a new amount for the same id. The function writes
    that amount, a new content hash and ``updated_at``, and keeps each other
    field. It skips a flagged row, an equal amount, and a duplicate whose id
    has no stored row (a match through the reference or the counterparty).
    It also skips a row when the incoming currency is not the stored currency.
    An amount in one currency must not replace an amount in another currency.
    It handles each id once.
    """
    corrections: list[dict[str, Any]] = []
    seen: set[str] = set()
    for trans in duplicates:
        trans_id = generate_transaction_id(trans)
        if trans_id in seen:
            continue
        seen.add(trans_id)
        new_amount = trans.get("amount")
        row = db.get(Transaction, trans_id)
        if row is None or row.deleted_at is not None or new_amount is None:
            continue
        if (trans.get("currency") or DEFAULT_CURRENCY) != (row.currency or DEFAULT_CURRENCY):
            logger.warning("amount_correction_skipped_currency", transaction_id=trans_id,
                           stored_currency=row.currency, incoming_currency=trans.get("currency"))
            continue
        if round(float(row.amount), 2) == round(float(new_amount), 2):
            continue
        old_amount = float(row.amount)
        row.amount = new_amount
        row.transaction_hash = calculate_transaction_hash_components(
            date_value=row.transactiondate,
            description=row.description,
            amount=new_amount,
            account=row.accountNumber,
        )
        row.updated_at = datetime.now()
        corrections.append(
            {"id": trans_id, "old_amount": old_amount, "new_amount": float(new_amount)}
        )
        logger.info("amount_corrected", transaction_id=trans_id,
                    old_amount=old_amount, new_amount=float(new_amount))
    if corrections:
        db.commit()
    return corrections


def import_file(
    db: Session,
    content: bytes,
    filename: str,
    statements_dir: Path,
    fmt: str = "auto",
) -> ImportSummary:
    """Import a statement file and return a summary.

    Steps: store the file, parse (by explicit ``fmt`` or extension), dedup against the
    DB, insert new rows, apply rules to the new rows, and count categorized vs not.

    Raises :class:`ImportError_` if the file yields no transactions.
    """
    if fmt not in VALID_FORMATS:
        raise ImportError_(f"Unknown format '{fmt}'. Expected one of {VALID_FORMATS}.")

    stored_path = _store_file(content, filename, statements_dir)
    original_name = Path(filename).name

    try:
        transactions = _parse(stored_path, fmt, db)
    except ImportError_:
        raise
    except Exception as exc:  # noqa: BLE001 - present a clean message to the caller
        raise ImportError_(f"Could not parse '{original_name}': {exc}") from exc

    if not transactions:
        raise ImportError_(
            f"No transactions found in '{original_name}'. "
            "Check the file format or choose an explicit format."
        )

    # The account CASH holds the hand-entered rows only. Refuse the whole file
    # before the first write, so that a refused file writes no row.
    try:
        reject_reserved_account(transactions)
    except ReservedAccountError as exc:
        raise ImportError_(f"Could not import '{original_name}': {exc}") from exc

    # Keep the user-facing source file name stable (not the stored uuid-prefixed name).
    for trans in transactions:
        trans["source_file"] = original_name

    new_transactions, duplicate_transactions = check_duplicates(db, transactions)
    new_ids = insert_transactions(db, new_transactions)
    apply_rules(db, transaction_ids=new_ids)
    # No rule matches on the amount, so a correction needs no rule run.
    corrections = correct_amounts(db, duplicate_transactions)

    categorized = 0
    if new_ids:
        categorized = (
            db.query(Transaction)
            .filter(Transaction.id.in_(new_ids), Transaction.category.isnot(None))
            .count()
        )

    return ImportSummary(
        source_file=original_name,
        new=len(new_ids),
        duplicates=len(duplicate_transactions) - len(corrections),
        categorized=categorized,
        uncategorized=len(new_ids) - categorized,
        corrected=len(corrections),
        new_ids=new_ids,
        corrections=corrections,
    )
