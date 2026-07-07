"""Deterministic transaction identity and duplicate handling (ported)."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from .models import Transaction
from .utils import calculate_transaction_hash_components, normalize_category

DEFAULT_CURRENCY = "EUR"


def generate_transaction_id(trans: dict[str, Any]) -> str:
    """Generate a deterministic unique ID for a transaction.

    PayPal: ``account_paypal_transaction_id``. Wise: ``account_wise_transaction_id``.
    SEB: ``account_seb_voucher_id``. Otherwise ``account_date_amount_deschash``.
    """
    account = str(trans.get("accountNumber", ""))

    paypal_txn_id = trans.get("paypal_transaction_id")
    if paypal_txn_id:
        return f"{account}_{paypal_txn_id}"

    wise_txn_id = trans.get("wise_transaction_id")
    if wise_txn_id:
        return f"{account}_{wise_txn_id}"

    seb_voucher_id = trans.get("seb_voucher_id")
    if seb_voucher_id:
        return f"{account}_{seb_voucher_id}"

    date = str(trans.get("transactiondate", ""))
    amount = str(trans.get("amount", ""))
    description = str(trans.get("description", ""))
    desc_hash = hashlib.md5(description.encode("utf-8")).hexdigest()[:16]
    return f"{account}_{date}_{amount}_{desc_hash}"


def check_duplicates(
    db: Session, transactions: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split incoming transactions into (new, duplicate) using deterministic ids.

    Duplicate = id already present in the DB, or a duplicate id within the batch.
    """
    incoming_ids: dict[str, dict[str, Any]] = {}
    duplicate_transactions: list[dict[str, Any]] = []

    for trans in transactions:
        trans_id = generate_transaction_id(trans)
        if trans_id in incoming_ids:
            # In-batch duplicate.
            duplicate_transactions.append(trans)
        else:
            incoming_ids[trans_id] = trans

    existing_ids: set[str] = set()
    if incoming_ids:
        existing_ids = {row[0] for row in db.query(Transaction.id).all()}

    new_transactions: list[dict[str, Any]] = []
    for trans_id, trans in incoming_ids.items():
        if trans_id in existing_ids:
            duplicate_transactions.append(trans)
        else:
            new_transactions.append(trans)

    return new_transactions, duplicate_transactions


def insert_transactions(db: Session, transactions: list[dict[str, Any]]) -> list[str]:
    """Insert transactions, returning the list of ids written.

    Uses ``db.merge`` so re-inserting an existing id is idempotent (exact duplicates
    are silently absorbed). Callers that need duplicate counts should call
    :func:`check_duplicates` first.
    """
    written: list[str] = []
    for trans in transactions:
        trans_id = generate_transaction_id(trans)
        transaction_hash = calculate_transaction_hash_components(
            date_value=trans.get("transactiondate"),
            description=trans.get("description"),
            amount=trans.get("amount"),
            account=trans.get("accountNumber"),
        )
        db_transaction = Transaction(
            id=trans_id,
            accountNumber=trans.get("accountNumber", ""),
            mutationcode=trans.get("mutationcode"),
            transactiondate=trans.get("transactiondate"),
            valuedate=trans.get("valuedate"),
            startsaldo=trans.get("startsaldo"),
            endsaldo=trans.get("endsaldo"),
            amount=trans.get("amount"),
            description=trans.get("description"),
            description_structured=trans.get("description_structured"),
            category=normalize_category(trans.get("category")) or trans.get("category"),
            manual_category=(
                normalize_category(trans.get("manual_category"))
                or trans.get("manual_category")
            ),
            tags=trans.get("tags"),
            manual_tags=trans.get("manual_tags"),
            categorization_source=trans.get("categorization_source"),
            currency=trans.get("currency", DEFAULT_CURRENCY),
            source_file=trans.get("source_file"),
            source_line=trans.get("source_line"),
            transaction_type_code=trans.get("transaction_type_code"),
            transaction_reference=trans.get("transaction_reference"),
            transaction_hash=transaction_hash,
        )
        db.merge(db_transaction)
        written.append(trans_id)
    db.commit()
    return written
