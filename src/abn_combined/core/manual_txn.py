"""Hand-entered transactions: the creation, the edit, the flag, and the purge.

A hand-entered transaction records a payment that no statement reports, for
example a cash payment. Four properties separate it from an imported
transaction.

- The id is a UUID. It does not come from the content, so an edit keeps it.
- ``is_manual`` is true. Only such a row accepts an edit and a removal flag.
- The account is the reserved pseudo account ``CASH``. No parser and no
  downloader writes to this account.
- The typed category goes to ``manual_category`` and the typed tags go to
  ``manual_tags``. ``categorization_source`` is ``"manual"``. A rule
  reapplication therefore never replaces them. A tag-only rule still adds a tag
  to ``tags``, exactly as it does for an imported transaction.

A removal is a flag, not a delete. ``flag`` writes ``deleted_at`` and ``restore``
clears it. The row stays in the table, and it travels in a snapshot with its
flag. Only :func:`purge_flagged_transactions` deletes a row, and it copies the
database first.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..constants import CASH_ACCOUNT
from ..logging_config import get_logger
from .dedup import DEFAULT_CURRENCY
from .models import Transaction
from .snapshots import _backup_db
from .utils import calculate_transaction_hash_components, normalize_category

logger = get_logger(__name__)

MANUAL_SOURCE = "manual"


class ManualTransactionError(ValueError):
    """The system refuses a hand-entered transaction operation.

    The message holds the reason, so a route can show it to the user.
    """


def _clean_tags(tags: Any) -> str | None:
    """Return the tags as a comma-separated string, or None for no tag."""
    if not tags:
        return None
    parts = [part.strip() for part in str(tags).split(",") if part.strip()]
    return ", ".join(parts) if parts else None


def _validate(
    transactiondate: date_type | None, amount: Any, description: Any
) -> tuple[date_type, float, str]:
    """Check the three required values, and return them in their stored form.

    Raise :class:`ManualTransactionError` with the reason for each rejection.
    """
    if not transactiondate:
        raise ManualTransactionError("The transaction needs a date.")

    if amount is None or amount == "":
        raise ManualTransactionError("The transaction needs an amount.")
    try:
        amount_value = float(amount)
    except (TypeError, ValueError) as exc:
        raise ManualTransactionError("The amount is not a number.") from exc
    if amount_value == 0:
        raise ManualTransactionError("The amount must not be zero.")

    description_value = str(description or "").strip()
    if not description_value:
        raise ManualTransactionError("The transaction needs a description.")

    return transactiondate, amount_value, description_value


def _content_hash(
    transactiondate: date_type, amount: float, description: str
) -> str:
    """Compute the content hash from the same components as for an import."""
    return calculate_transaction_hash_components(
        date_value=transactiondate,
        description=description,
        amount=amount,
        account=CASH_ACCOUNT,
    )


def _get_manual_row(db: Session, transaction_id: str) -> Transaction:
    """Load one hand-entered row, or raise the reason for the refusal."""
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).one_or_none()
    if txn is None:
        raise ManualTransactionError(f"The transaction {transaction_id} is not found.")
    if not txn.is_manual:
        raise ManualTransactionError(
            f"The transaction {transaction_id} is not hand-entered. "
            "Only a hand-entered transaction accepts this operation."
        )
    return txn


def create_manual_transaction(
    db: Session,
    *,
    transactiondate: date_type | None,
    amount: Any,
    description: Any,
    category: str | None = None,
    tags: str | None = None,
    currency: str = DEFAULT_CURRENCY,
    commit: bool = True,
) -> Transaction:
    """Create one hand-entered transaction in the pseudo account ``CASH``.

    The date, the amount, and the description are required. The amount must not
    be zero. The function writes nothing when it refuses a value.
    """
    txn_date, amount_value, description_value = _validate(
        transactiondate, amount, description
    )

    txn = Transaction(
        id=str(uuid.uuid4()),
        accountNumber=CASH_ACCOUNT,
        transactiondate=txn_date,
        amount=amount_value,
        description=description_value,
        manual_category=normalize_category(category),
        manual_tags=_clean_tags(tags),
        categorization_source=MANUAL_SOURCE,
        currency=currency or DEFAULT_CURRENCY,
        transaction_hash=_content_hash(txn_date, amount_value, description_value),
        updated_at=datetime.now(),
        is_manual=True,
        deleted_at=None,
    )
    db.add(txn)
    if commit:
        db.commit()
    logger.info("manual_txn_created", txn=txn.id, amount=amount_value)
    return txn


def edit_manual_transaction(
    db: Session,
    transaction_id: str,
    *,
    transactiondate: date_type | None,
    amount: Any,
    description: Any,
    category: str | None = None,
    tags: str | None = None,
    commit: bool = True,
) -> Transaction:
    """Change one hand-entered transaction, and keep its id.

    The function recomputes the content hash and stamps ``updated_at``, so that a
    delta snapshot holds the new values. The function refuses an imported row.
    """
    txn = _get_manual_row(db, transaction_id)
    txn_date, amount_value, description_value = _validate(
        transactiondate, amount, description
    )

    txn.transactiondate = txn_date
    txn.amount = amount_value
    txn.description = description_value
    txn.manual_category = normalize_category(category)
    txn.manual_tags = _clean_tags(tags)
    txn.categorization_source = MANUAL_SOURCE
    txn.transaction_hash = _content_hash(txn_date, amount_value, description_value)
    txn.updated_at = datetime.now()
    if commit:
        db.commit()
    logger.info("manual_txn_edited", txn=txn.id, amount=amount_value)
    return txn


def flag_manual_transaction(
    db: Session, transaction_id: str, *, commit: bool = True
) -> Transaction:
    """Flag one hand-entered transaction for removal.

    The function writes the time of the flag to ``deleted_at``. The row stays in
    the database. The function refuses an imported row.
    """
    txn = _get_manual_row(db, transaction_id)
    now = datetime.now()
    txn.deleted_at = now
    txn.updated_at = now
    if commit:
        db.commit()
    logger.info("manual_txn_flagged", txn=txn.id)
    return txn


def restore_manual_transaction(
    db: Session, transaction_id: str, *, commit: bool = True
) -> Transaction:
    """Remove the removal flag from one hand-entered transaction.

    The row appears again in each list and in each total. The function refuses an
    imported row.
    """
    txn = _get_manual_row(db, transaction_id)
    txn.deleted_at = None
    txn.updated_at = datetime.now()
    if commit:
        db.commit()
    logger.info("manual_txn_restored", txn=txn.id)
    return txn


def purge_flagged_transactions(db: Session, db_path: Path) -> int:
    """Delete each flagged transaction, and return the number of deleted rows.

    Caution: the application cannot undo the purge. Ask the user to confirm it
    first.

    The function copies the database to a timestamped backup beside it before it
    deletes a row. It uses the same backup helper as the snapshot import. It
    deletes no row that holds no flag.
    """
    db.commit()
    db_file = Path(db_path)
    if db_file.exists():
        _backup_db(db_file)

    deleted = (
        db.query(Transaction)
        .filter(Transaction.deleted_at.isnot(None))
        .delete(synchronize_session="fetch")
    )
    db.commit()
    logger.info("manual_txn_purged", count=deleted)
    return int(deleted)
