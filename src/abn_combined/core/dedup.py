"""Deterministic transaction identity and duplicate handling (ported)."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from ..constants import CASH_ACCOUNT, is_reserved_account
from .models import Transaction
from .utils import calculate_transaction_hash_components, normalize_category

DEFAULT_CURRENCY = "EUR"

# A reference that names no single payment. The bank writes one of these when
# the payment carries no reference, so many rows share the value. The sample
# statement of 2291 rows holds `NOTPROVIDED` 136 times.
_UNUSABLE_REFERENCES = frozenset({"NONREF", "NOTPROVIDED"})

# The separators that `normalize_reference` removes. An MT940 description wraps
# at a fixed width, and the wrap can fall inside the reference. The bank also
# prints the same reference with different separators in the two description
# forms. One payment therefore reads `8022764496926345` in one form and
# `8022.7644 .9692.6345` in the other.
_REFERENCE_SEPARATORS = re.compile(r"[\s.\-]+")


def normalize_reference(value: str) -> str:
    """Return the comparison form of a reference.

    The function removes each whitespace character, each period, and each
    hyphen, and then changes the text to upper case. Two forms of one reference
    therefore give one key.

    The system stores the original text, and it compares this form. The rule
    matching normalizes in the same manner, through
    :func:`core.utils.normalize_string_for_matching`.
    """
    return _REFERENCE_SEPARATORS.sub("", value).upper()


def format_krona(value: Any) -> str:
    """Return an SEB krona value as id text: 2 decimal places, half up.

    A missing value gives an empty text. The iOS app formats the value in the
    same manner, and ``tests/fixtures/seb_ids.json`` holds the shared cases.
    """
    if value is None or value == "":
        return ""
    exact = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(exact, "f")


def seb_voucher_key(
    account: str, voucher: str, booking_date: Any, amount: Any, balance: Any
) -> str:
    """Return the id of an SEB transaction.

    SEB gives one voucher number to many card payments. The id therefore also
    holds the booking date (``YYYY-MM-DD``), the krona amount, and the krona
    balance. The krona values do not change when the ECB rate changes.
    """
    return "_".join(
        (account, voucher, str(booking_date)[:10], format_krona(amount), format_krona(balance))
    )


class ReservedAccountError(ValueError):
    """An import names the reserved pseudo account of the hand-entered rows."""


def generate_transaction_id(trans: dict[str, Any]) -> str:
    """Generate a deterministic unique ID for a transaction.

    PayPal: ``account_paypal_transaction_id``. Wise: ``account_wise_transaction_id``.
    SEB: the SEB voucher key (see :func:`seb_voucher_key`). First Tech:
    ``account_ftfcu_fitid``.
    Otherwise ``account_date_amount_deschash``.
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
        return seb_voucher_key(
            account,
            str(seb_voucher_id),
            trans.get("transactiondate", ""),
            trans.get("seb_native_amount"),
            trans.get("seb_native_balance"),
        )

    ftfcu_fitid = trans.get("ftfcu_fitid")
    if ftfcu_fitid:
        return f"{account}_{ftfcu_fitid}"

    date = str(trans.get("transactiondate", ""))
    amount = str(trans.get("amount", ""))
    description = str(trans.get("description", ""))
    desc_hash = hashlib.md5(description.encode("utf-8")).hexdigest()[:16]
    return f"{account}_{date}_{amount}_{desc_hash}"


def extract_end_to_end_reference(trans: dict[str, Any]) -> str | None:
    """Return the usable end-to-end reference of a parsed transaction.

    The value comes from the structured description. The function returns the
    original text, because the system stores it and shows it. Each comparison
    uses :func:`normalize_reference`.

    The function returns None for an empty value and for a value that names no
    single payment, such as ``NONREF``. The duplicate check must not join two
    payments on such a value.
    """
    value = trans.get("end_to_end_reference")

    if value is None:
        structured = trans.get("description_structured")
        if isinstance(structured, str) and structured:
            try:
                data = json.loads(structured)
            except ValueError:
                data = None
            if isinstance(data, dict):
                value = data.get("end_to_end_reference")
        elif isinstance(structured, dict):
            value = structured.get("end_to_end_reference")

    if not isinstance(value, str):
        return None

    value = value.strip()
    if not value:
        return None
    if normalize_reference(value) in _UNUSABLE_REFERENCES:
        return None
    return value


def _structured(trans: dict[str, Any]) -> dict[str, Any]:
    """Return the structured description of a parsed transaction, as a dict."""
    structured = trans.get("description_structured")
    if isinstance(structured, dict):
        return structured
    if isinstance(structured, str) and structured:
        try:
            data = json.loads(structured)
        except ValueError:
            return {}
        if isinstance(data, dict):
            return data
    return {}


def _source_file(trans: dict[str, Any]) -> str:
    """Return the source file of a parsed transaction, as a string."""
    return str(trans.get("source_file") or "")


def counterparty_key(
    trans: dict[str, Any],
) -> tuple[str, str, str, str, str] | None:
    """Return the second match key, or None when it does not apply.

    The key is the account, the transaction date, the amount, the normalized
    counterparty IBAN, and the normalized remittance text. A transfer between
    two accounts of the user carries no end-to-end reference, so only this key
    joins its two description forms.

    The key holds the remittance text, because two payments of one day can
    share an account, an amount, and a counterparty. A real database holds
    three payments of -149,00 euro of one day to one PayPal IBAN, and only
    their remittance texts differ.

    The function returns None when the transaction holds a usable reference,
    because the reference key already covers it, and None when the transaction
    holds no counterparty IBAN.
    """
    if extract_end_to_end_reference(trans) is not None:
        return None

    data = _structured(trans)
    iban = data.get("iban")
    if not isinstance(iban, str) or not iban.strip():
        return None

    remittance = data.get("remittance_info")
    if not isinstance(remittance, str):
        remittance = ""

    return (
        str(trans.get("accountNumber", "")),
        str(trans.get("transactiondate", "")),
        _amount_key(trans.get("amount")),
        normalize_reference(iban),
        normalize_reference(remittance),
    )


def _reference_key(trans: dict[str, Any]) -> tuple[str, str, str] | None:
    """Return the (account, reference, amount) match key, or None if none.

    The key holds the account, because a reference is unique for one creditor
    and not for the world.

    The key also holds the amount. A reversal carries the reference of the
    payment that it reverses, with the opposite sign. The sample statement
    holds three such pairs, for example a direct debit of -149,88 and its
    `SEPA INCASSO TERUGBOEKING` of +149,88. Those are two transactions, and the
    check must not join them. The two description forms of one payment always
    report the same amount, because they describe one statement line.
    """
    reference = extract_end_to_end_reference(trans)
    if reference is None:
        return None
    return (
        str(trans.get("accountNumber", "")),
        normalize_reference(reference),
        _amount_key(trans.get("amount")),
    )


def _amount_key(amount: Any) -> str:
    """Return the amount as a stable string with two decimal places."""
    if amount is None:
        return ""
    try:
        return f"{Decimal(str(amount)):.2f}"
    except (ArithmeticError, ValueError):
        return str(amount)


def reject_reserved_account(transactions: list[dict[str, Any]]) -> None:
    """Refuse the batch if one transaction names the reserved pseudo account.

    The account ``CASH`` belongs to the hand-entered transactions only. The
    function checks the whole batch before the caller writes a row, so that a
    refused batch writes nothing. Raise :class:`ReservedAccountError` with the
    name of the reserved account.
    """
    for trans in transactions:
        if is_reserved_account(trans.get("accountNumber")):
            raise ReservedAccountError(
                f"The account {CASH_ACCOUNT} is reserved for the hand-entered "
                "transactions. An import must not write a transaction to it."
            )


def check_duplicates(
    db: Session, transactions: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split incoming transactions into (new, duplicate) using deterministic ids.

    Duplicate = id already present in the DB, or a duplicate id within the batch.

    An imported transaction never matches a hand-entered transaction. The id of a
    hand-entered row is a UUID, and the id of an imported row holds the account,
    the date, the amount, and a hash of the description. The two forms cannot
    collide. The check reads each stored id, which includes the id of a flagged
    row. A flagged id therefore stays taken, and a second row cannot claim it.

    The check also matches the account with the end-to-end reference. The bank
    writes one SEPA payment in two description forms, and the two forms hold a
    different raw text. The id of the two forms therefore differs, and only the
    reference joins them. The check ignores an empty reference and a reference
    that names no single payment, such as ``NONREF``.

    The comparison of the reference uses :func:`normalize_reference`, because
    the two forms can print one reference with different separators.

    A transfer between two accounts of the user carries no reference. For such a
    transaction the check uses :func:`counterparty_key`, which holds the
    counterparty IBAN and the remittance text. It joins two such rows only when
    they come from two statement files, because two rows of one file are two
    payments.
    """
    incoming_ids: dict[str, dict[str, Any]] = {}
    incoming_references: dict[tuple[str, str, str], str] = {}
    # The counterparty key maps to the source file of the row that claimed it.
    # Two rows of one file are two payments, and never two forms of one payment.
    incoming_counterparties: dict[tuple[str, str, str, str, str], str] = {}
    duplicate_transactions: list[dict[str, Any]] = []

    for trans in transactions:
        trans_id = generate_transaction_id(trans)
        if trans_id in incoming_ids:
            # In-batch duplicate by the id.
            duplicate_transactions.append(trans)
            continue

        reference_key = _reference_key(trans)
        if reference_key is not None and reference_key in incoming_references:
            # In-batch duplicate by the reference: the second description form
            # of a payment that an earlier row of this batch already holds.
            duplicate_transactions.append(trans)
            continue

        other_key = counterparty_key(trans)
        if other_key is not None:
            claimed_from = incoming_counterparties.get(other_key)
            if claimed_from is not None and claimed_from != _source_file(trans):
                # The second description form of a transfer that carries no
                # reference. The two rows come from two statement files.
                duplicate_transactions.append(trans)
                continue

        incoming_ids[trans_id] = trans
        if reference_key is not None:
            incoming_references[reference_key] = trans_id
        if other_key is not None and other_key not in incoming_counterparties:
            incoming_counterparties[other_key] = _source_file(trans)

    existing_ids: set[str] = set()
    existing_references: set[tuple[str, str, str]] = set()
    existing_counterparties: dict[tuple[str, str, str, str, str], str] = {}
    if incoming_ids:
        existing_ids = {row[0] for row in db.query(Transaction.id).all()}
        # The column holds the original text, so the comparison normalizes each
        # stored value as well.
        existing_references = {
            (
                str(account),
                normalize_reference(reference),
                _amount_key(amount),
            )
            for account, reference, amount in db.query(
                Transaction.accountNumber,
                Transaction.end_to_end_reference,
                Transaction.amount,
            )
            .filter(Transaction.end_to_end_reference.isnot(None))
            .all()
            if reference
        }

    if incoming_counterparties:
        # Build the stored side with the same function, so that it agrees with
        # the incoming side. Only a row with a structured description can hold
        # this key.
        for row in (
            db.query(
                Transaction.accountNumber,
                Transaction.transactiondate,
                Transaction.amount,
                Transaction.description_structured,
                Transaction.end_to_end_reference,
                Transaction.source_file,
            )
            .filter(Transaction.description_structured.isnot(None))
            .all()
        ):
            stored_key = counterparty_key(
                {
                    "accountNumber": row[0],
                    "transactiondate": row[1],
                    "amount": row[2],
                    "description_structured": row[3],
                    "end_to_end_reference": row[4],
                }
            )
            if stored_key is not None and stored_key not in existing_counterparties:
                existing_counterparties[stored_key] = str(row[5] or "")

    new_transactions: list[dict[str, Any]] = []
    for trans_id, trans in incoming_ids.items():
        if trans_id in existing_ids:
            duplicate_transactions.append(trans)
            continue
        reference_key = _reference_key(trans)
        if reference_key is not None and reference_key in existing_references:
            duplicate_transactions.append(trans)
            continue
        other_key = counterparty_key(trans)
        if other_key is not None:
            stored_from = existing_counterparties.get(other_key)
            if stored_from is not None and stored_from != _source_file(trans):
                duplicate_transactions.append(trans)
                continue
        new_transactions.append(trans)

    return new_transactions, duplicate_transactions


def insert_transactions(db: Session, transactions: list[dict[str, Any]]) -> list[str]:
    """Insert transactions, returning the list of ids written.

    Uses ``db.merge`` so re-inserting an existing id is idempotent (exact duplicates
    are silently absorbed). Callers that need duplicate counts should call
    :func:`check_duplicates` first.
    """
    reject_reserved_account(transactions)

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
            end_to_end_reference=extract_end_to_end_reference(trans),
            transaction_hash=transaction_hash,
        )
        db.merge(db_transaction)
        written.append(trans_id)
    db.commit()
    return written
