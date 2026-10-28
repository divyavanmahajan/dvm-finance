"""Hand-entered transaction tests: creation, edit, flag, restore, purge."""

from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from abn_combined.constants import CASH_ACCOUNT
from abn_combined.core.dedup import insert_transactions
from abn_combined.core.importer import ImportError_
from abn_combined.core.manual_txn import (
    ManualTransactionError,
    create_manual_transaction,
    edit_manual_transaction,
    flag_manual_transaction,
    purge_flagged_transactions,
    restore_manual_transaction,
)
from abn_combined.core.models import Base, Transaction
from abn_combined.core.utils import calculate_transaction_hash_components


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "t.db"


@pytest.fixture
def session(db_path):
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _create(session, **over):
    kwargs = {
        "transactiondate": date(2024, 3, 1),
        "amount": -20.00,
        "description": "Cash payment at the market",
    }
    kwargs.update(over)
    return create_manual_transaction(session, **kwargs)


def _imported(**over):
    base = {
        "accountNumber": "869623141",
        "transactiondate": date(2024, 3, 1),
        "amount": -20.00,
        "description": "Cash payment at the market",
        "currency": "EUR",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# 2.1 Creation
# ---------------------------------------------------------------------------


def test_create_gives_the_row_a_uuid_id(session):
    txn = _create(session)
    # The id parses as a UUID, and the string form matches the canonical form.
    assert txn.id == str(uuid.UUID(txn.id))


def test_create_writes_the_manual_fields(session):
    txn = _create(session, category="Groceries", tags="cash, market")
    assert txn.is_manual is True
    assert txn.accountNumber == CASH_ACCOUNT
    assert txn.manual_category == "groceries"
    assert txn.manual_tags == "cash, market"
    assert txn.categorization_source == "manual"
    assert txn.currency == "EUR"
    assert txn.deleted_at is None
    assert txn.updated_at is not None


def test_create_leaves_the_rule_fields_free(session):
    # A tag-only rule must still write ``tags`` later, so creation keeps it empty.
    txn = _create(session, category="Groceries", tags="cash")
    assert txn.category is None
    assert txn.tags is None


def test_create_stores_the_content_hash(session):
    txn = _create(session)
    expected = calculate_transaction_hash_components(
        date_value=date(2024, 3, 1),
        description="Cash payment at the market",
        amount=-20.00,
        account=CASH_ACCOUNT,
    )
    assert txn.transaction_hash == expected


def test_create_persists_one_row(session):
    txn = _create(session)
    session.expire_all()
    rows = session.query(Transaction).all()
    assert len(rows) == 1
    assert rows[0].id == txn.id


def test_create_rejects_a_missing_date(session):
    with pytest.raises(ManualTransactionError, match="date"):
        _create(session, transactiondate=None)
    assert session.query(Transaction).count() == 0


def test_create_rejects_a_missing_amount(session):
    with pytest.raises(ManualTransactionError, match="amount"):
        _create(session, amount=None)
    assert session.query(Transaction).count() == 0


def test_create_rejects_a_zero_amount(session):
    with pytest.raises(ManualTransactionError, match="amount"):
        _create(session, amount=0)
    assert session.query(Transaction).count() == 0


def test_create_rejects_a_missing_description(session):
    with pytest.raises(ManualTransactionError, match="description"):
        _create(session, description="   ")
    assert session.query(Transaction).count() == 0


# ---------------------------------------------------------------------------
# 2.2 Edit
# ---------------------------------------------------------------------------


def test_edit_keeps_the_id(session):
    txn = _create(session)
    before = txn.id
    edited = edit_manual_transaction(
        session,
        before,
        transactiondate=date(2024, 4, 2),
        amount=-25.50,
        description="Cash payment at the bakery",
    )
    assert edited.id == before
    assert session.query(Transaction).count() == 1


def test_edit_writes_the_new_values(session):
    txn = _create(session, category="Groceries", tags="cash")
    edited = edit_manual_transaction(
        session,
        txn.id,
        transactiondate=date(2024, 4, 2),
        amount=-25.50,
        description="Cash payment at the bakery",
        category="Bakery",
        tags="cash, bakery",
    )
    assert edited.transactiondate == date(2024, 4, 2)
    assert float(edited.amount) == -25.50
    assert edited.description == "Cash payment at the bakery"
    assert edited.manual_category == "bakery"
    assert edited.manual_tags == "cash, bakery"
    assert edited.categorization_source == "manual"


def test_edit_recomputes_the_content_hash(session):
    txn = _create(session)
    old_hash = txn.transaction_hash
    edited = edit_manual_transaction(
        session,
        txn.id,
        transactiondate=date(2024, 3, 1),
        amount=-20.00,
        description="Cash payment at the bakery",
    )
    expected = calculate_transaction_hash_components(
        date_value=date(2024, 3, 1),
        description="Cash payment at the bakery",
        amount=-20.00,
        account=CASH_ACCOUNT,
    )
    assert edited.transaction_hash == expected
    assert edited.transaction_hash != old_hash


def test_edit_stamps_updated_at(session):
    txn = _create(session)
    txn.updated_at = datetime(2020, 1, 1)
    session.commit()
    edited = edit_manual_transaction(
        session,
        txn.id,
        transactiondate=date(2024, 3, 1),
        amount=-21.00,
        description="Cash payment at the market",
    )
    assert edited.updated_at > datetime(2020, 1, 1)


def test_edit_refuses_an_imported_row(session):
    ids = insert_transactions(session, [_imported()])
    with pytest.raises(ManualTransactionError, match="hand-entered"):
        edit_manual_transaction(
            session,
            ids[0],
            transactiondate=date(2024, 3, 1),
            amount=-1.00,
            description="Changed",
        )
    row = session.query(Transaction).filter_by(id=ids[0]).one()
    assert float(row.amount) == -20.00


def test_edit_refuses_an_unknown_id(session):
    with pytest.raises(ManualTransactionError, match="not found"):
        edit_manual_transaction(
            session,
            "no-such-id",
            transactiondate=date(2024, 3, 1),
            amount=-1.00,
            description="Changed",
        )


def test_edit_rejects_a_zero_amount(session):
    txn = _create(session)
    with pytest.raises(ManualTransactionError, match="amount"):
        edit_manual_transaction(
            session,
            txn.id,
            transactiondate=date(2024, 3, 1),
            amount=0,
            description="Cash payment at the market",
        )


# ---------------------------------------------------------------------------
# 2.3 The import pipeline refuses the reserved account
# ---------------------------------------------------------------------------


def test_insert_refuses_the_reserved_account(session):
    with pytest.raises(ValueError, match=CASH_ACCOUNT):
        insert_transactions(session, [_imported(accountNumber=CASH_ACCOUNT)])
    assert session.query(Transaction).count() == 0


def test_insert_refuses_the_reserved_account_in_any_case(session):
    with pytest.raises(ValueError, match=CASH_ACCOUNT):
        insert_transactions(session, [_imported(accountNumber=" cash ")])
    assert session.query(Transaction).count() == 0


def test_insert_writes_no_row_when_one_row_names_the_reserved_account(session):
    rows = [_imported(), _imported(accountNumber=CASH_ACCOUNT, description="Other")]
    with pytest.raises(ValueError, match=CASH_ACCOUNT):
        insert_transactions(session, rows)
    assert session.query(Transaction).count() == 0


def test_import_file_refuses_the_reserved_account(session, tmp_path, monkeypatch):
    from abn_combined.core import importer

    rows = [_imported(accountNumber=CASH_ACCOUNT)]
    monkeypatch.setattr(importer, "_parse", lambda path, fmt, db: list(rows))
    with pytest.raises(ImportError_, match=CASH_ACCOUNT):
        importer.import_file(session, b"stub", "statement.csv", tmp_path / "statements")
    assert session.query(Transaction).count() == 0


# ---------------------------------------------------------------------------
# 3.1 The flag and the restore
# ---------------------------------------------------------------------------


def test_flag_keeps_the_row_and_stamps_the_time(session):
    txn = _create(session)
    flagged = flag_manual_transaction(session, txn.id)
    assert flagged.deleted_at is not None
    assert session.query(Transaction).count() == 1


def test_flag_stamps_updated_at(session):
    txn = _create(session)
    txn.updated_at = datetime(2020, 1, 1)
    session.commit()
    flagged = flag_manual_transaction(session, txn.id)
    assert flagged.updated_at > datetime(2020, 1, 1)


def test_restore_clears_the_flag(session):
    txn = _create(session)
    flag_manual_transaction(session, txn.id)
    restored = restore_manual_transaction(session, txn.id)
    assert restored.deleted_at is None
    assert restored.updated_at is not None


def test_flag_refuses_an_imported_row(session):
    ids = insert_transactions(session, [_imported()])
    with pytest.raises(ManualTransactionError, match="hand-entered"):
        flag_manual_transaction(session, ids[0])
    row = session.query(Transaction).filter_by(id=ids[0]).one()
    assert row.deleted_at is None


def test_restore_refuses_an_imported_row(session):
    ids = insert_transactions(session, [_imported()])
    with pytest.raises(ManualTransactionError, match="hand-entered"):
        restore_manual_transaction(session, ids[0])


def test_flag_refuses_an_unknown_id(session):
    with pytest.raises(ManualTransactionError, match="not found"):
        flag_manual_transaction(session, "no-such-id")


# ---------------------------------------------------------------------------
# 6.1 The purge
# ---------------------------------------------------------------------------


def _backups(db_path):
    return sorted(db_path.parent.glob(f"{db_path.stem}.backup-*{db_path.suffix}"))


def test_purge_deletes_each_flagged_row_and_reports_the_count(session, db_path):
    first = _create(session, description="First cash payment")
    second = _create(session, description="Second cash payment")
    live = _create(session, description="Live cash payment")
    flag_manual_transaction(session, first.id)
    flag_manual_transaction(session, second.id)

    count = purge_flagged_transactions(session, db_path)

    assert count == 2
    remaining = [row.id for row in session.query(Transaction).all()]
    assert remaining == [live.id]


def test_purge_writes_a_backup_first(session, db_path):
    txn = _create(session)
    flag_manual_transaction(session, txn.id)

    purge_flagged_transactions(session, db_path)

    backups = _backups(db_path)
    assert len(backups) == 1
    assert backups[0].stat().st_size > 0
    # The backup still holds the flagged row.
    engine = create_engine(f"sqlite:///{backups[0]}")
    with Session(engine) as backup_session:
        assert backup_session.query(Transaction).count() == 1


def test_purge_keeps_an_imported_row(session, db_path):
    ids = insert_transactions(session, [_imported()])
    txn = _create(session)
    flag_manual_transaction(session, txn.id)

    assert purge_flagged_transactions(session, db_path) == 1
    remaining = [row.id for row in session.query(Transaction).all()]
    assert remaining == [ids[0]]


def test_purge_reports_zero_for_an_empty_database(session, db_path):
    assert purge_flagged_transactions(session, db_path) == 0


def test_purge_reports_zero_when_no_row_holds_a_flag(session, db_path):
    txn = _create(session)
    assert purge_flagged_transactions(session, db_path) == 0
    assert session.query(Transaction).filter_by(id=txn.id).count() == 1
