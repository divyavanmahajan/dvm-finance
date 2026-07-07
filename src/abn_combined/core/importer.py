"""Unified import pipeline: parse -> dedup -> insert -> apply rules -> summary."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from ..parsers import (
    parse_csv_file,
    parse_paypal_file,
    parse_seb_file,
    parse_statement_file,
    parse_wise_file,
)
from .categorizer import apply_rules
from .dedup import check_duplicates, insert_transactions
from .models import Transaction

# Explicit format overrides (auto = detect by extension via parse_statement_file).
VALID_FORMATS = ("auto", "paypal", "wise", "seb", "csv")


class ImportError_(ValueError):
    """Raised when a file cannot be parsed into any transactions."""


@dataclass
class ImportSummary:
    source_file: str
    new: int = 0
    duplicates: int = 0
    categorized: int = 0
    uncategorized: int = 0
    new_ids: list[str] = field(default_factory=list)

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
    if fmt == "csv":
        return parse_csv_file(path)
    return parse_statement_file(path)


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

    # Keep the user-facing source file name stable (not the stored uuid-prefixed name).
    for trans in transactions:
        trans["source_file"] = original_name

    new_transactions, duplicate_transactions = check_duplicates(db, transactions)
    new_ids = insert_transactions(db, new_transactions)
    apply_rules(db, transaction_ids=new_ids)

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
        duplicates=len(duplicate_transactions),
        categorized=categorized,
        uncategorized=len(new_ids) - categorized,
        new_ids=new_ids,
    )
