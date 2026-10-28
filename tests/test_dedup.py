"""Deterministic id generation and duplicate handling tests."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from abn_combined.constants import CASH_ACCOUNT
from abn_combined.core.dedup import (
    ReservedAccountError,
    check_duplicates,
    generate_transaction_id,
    insert_transactions,
)
from abn_combined.core.manual_txn import (
    create_manual_transaction,
    flag_manual_transaction,
)
from abn_combined.core.models import Base, Transaction


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _txn(**over):
    base = {
        "accountNumber": "869623141",
        "transactiondate": date(2024, 1, 1),
        "amount": -5.75,
        "description": "BEA test shop",
        "currency": "EUR",
    }
    base.update(over)
    return base


def test_id_is_deterministic():
    assert generate_transaction_id(_txn()) == generate_transaction_id(_txn())


def test_id_changes_with_amount():
    assert generate_transaction_id(_txn()) != generate_transaction_id(_txn(amount=-6.00))


def test_id_changes_with_description():
    a = generate_transaction_id(_txn())
    b = generate_transaction_id(_txn(description="OTHER"))
    assert a != b


def test_paypal_id_recipe():
    tid = generate_transaction_id(_txn(accountNumber="pp:me", paypal_transaction_id="ABC123"))
    assert tid == "pp:me_ABC123"


def test_wise_and_seb_id_recipe():
    assert generate_transaction_id(_txn(wise_transaction_id="W1")).endswith("_W1")
    assert generate_transaction_id(_txn(seb_voucher_id="V9")).endswith("_V9")


def test_insert_and_dedup_counting(session):
    txns = [_txn(), _txn(amount=-10.0, description="second")]
    new, dup = check_duplicates(session, txns)
    assert len(new) == 2
    assert len(dup) == 0

    insert_transactions(session, new)
    assert session.query(Transaction).count() == 2

    # Re-importing the same batch reports all duplicates, inserts nothing new.
    new2, dup2 = check_duplicates(session, txns)
    assert len(new2) == 0
    assert len(dup2) == 2


def test_in_batch_duplicates_counted(session):
    txns = [_txn(), _txn()]  # identical -> same id
    new, dup = check_duplicates(session, txns)
    assert len(new) == 1
    assert len(dup) == 1


def test_transaction_hash_written(session):
    insert_transactions(session, [_txn()])
    row = session.query(Transaction).one()
    assert row.transaction_hash and len(row.transaction_hash) == 64


# ---------------------------------------------------------------------------
# Hand-entered transactions and the duplicate check
# ---------------------------------------------------------------------------


def test_two_hand_entered_rows_with_the_same_values_both_exist(session):
    first = create_manual_transaction(
        session,
        transactiondate=date(2024, 1, 1),
        amount=-5.75,
        description="Cash at the market",
    )
    second = create_manual_transaction(
        session,
        transactiondate=date(2024, 1, 1),
        amount=-5.75,
        description="Cash at the market",
    )
    assert first.id != second.id
    assert session.query(Transaction).count() == 2


def test_an_import_never_matches_a_hand_entered_row(session):
    manual = create_manual_transaction(
        session,
        transactiondate=date(2024, 1, 1),
        amount=-5.75,
        description="BEA test shop",
    )
    # The statement reports the same payment for a real bank account.
    new, duplicates = check_duplicates(session, [_txn()])
    assert len(new) == 1
    assert duplicates == []

    insert_transactions(session, new)
    ids = {row.id for row in session.query(Transaction).all()}
    assert manual.id in ids
    assert len(ids) == 2


def test_the_id_of_a_flagged_row_stays_taken(session):
    manual = create_manual_transaction(
        session,
        transactiondate=date(2024, 1, 1),
        amount=-5.75,
        description="Cash at the market",
    )
    flag_manual_transaction(session, manual.id)
    existing_ids = {row[0] for row in session.query(Transaction.id).all()}
    assert manual.id in existing_ids


def test_insert_refuses_the_reserved_account(session):
    with pytest.raises(ReservedAccountError):
        insert_transactions(session, [_txn(accountNumber=CASH_ACCOUNT)])
    assert session.query(Transaction).count() == 0
