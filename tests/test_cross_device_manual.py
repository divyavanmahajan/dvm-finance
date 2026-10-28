"""The cross-device behavior of the hand-entered transactions (task 9.2).

Each device creates its own hand-entered rows while it cannot see the other
device. The merge is therefore a union, because each row holds its own UUID. A
flag that one device sets reaches the other device, and the row becomes
invisible there.

See `openspec/changes/add-manual-transactions/design.md`, section "The UUID
makes the phone a first-class writer".
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from abn_combined.core.filters import TransactionFilter, paginate
from abn_combined.core.manual_txn import (
    create_manual_transaction,
    flag_manual_transaction,
)
from abn_combined.core.models import Base, Transaction
from abn_combined.core.snapshots import export_snapshot, import_snapshot, read_snapshot


def _make_db(tmp_path: Path, name: str) -> tuple[Session, Path]:
    data_dir = tmp_path / name
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "abn_combined.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)(), db_path


@pytest.fixture
def device_a(tmp_path):
    session, db_path = _make_db(tmp_path, "device_a")
    yield session, db_path
    session.close()


@pytest.fixture
def device_b(tmp_path):
    session, db_path = _make_db(tmp_path, "device_b")
    yield session, db_path
    session.close()


def _sync(source: Session, target: Session, target_path: Path, out_dir: Path) -> None:
    """Export a snapshot from *source*, and import it into *target*."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = export_snapshot(source, out_dir)
    import_snapshot(target, read_snapshot(path.read_bytes()), target_path)


def _visible_ids(db: Session) -> set[str]:
    """Return the id of each row that the transactions list shows."""
    page = paginate(db, TransactionFilter())
    return {row.id for row in page.items}


def test_each_device_keeps_the_rows_of_the_other_device(device_a, device_b, tmp_path):
    """Both devices create a cash row. The merge keeps both rows."""
    session_a, _path_a = device_a
    session_b, path_b = device_b

    row_a = create_manual_transaction(
        session_a,
        transactiondate=date(2026, 3, 1),
        amount=-20.00,
        description="Market",
        category="food",
    )
    row_b = create_manual_transaction(
        session_b,
        transactiondate=date(2026, 3, 2),
        amount=-5.00,
        description="Coffee",
        category="food",
    )
    assert row_a.id != row_b.id

    _sync(session_a, session_b, path_b, tmp_path / "from_a")

    assert _visible_ids(session_b) == {row_a.id, row_b.id}


def test_two_devices_record_the_same_payment_and_both_rows_survive(
    device_a, device_b, tmp_path
):
    """The same date, amount, and description do not collide.

    A content-derived id would give the two rows the same id, and the merge
    would keep only one of them. The UUID keeps both, and the user removes the
    row that is not necessary.
    """
    session_a, _path_a = device_a
    session_b, path_b = device_b

    values = {
        "transactiondate": date(2026, 3, 3),
        "amount": -12.50,
        "description": "Bakery",
    }
    row_a = create_manual_transaction(session_a, **values)
    row_b = create_manual_transaction(session_b, **values)
    assert row_a.id != row_b.id

    _sync(session_a, session_b, path_b, tmp_path / "from_a")

    assert _visible_ids(session_b) == {row_a.id, row_b.id}


def test_a_flag_on_one_device_hides_the_row_on_the_other_device(
    device_a, device_b, tmp_path
):
    """Device A flags a row. Device B hides the row after the next sync."""
    session_a, path_a = device_a
    session_b, path_b = device_b

    row_a = create_manual_transaction(
        session_a,
        transactiondate=date(2026, 3, 4),
        amount=-8.00,
        description="Tram ticket",
    )
    _sync(session_a, session_b, path_b, tmp_path / "from_a_first")
    assert row_a.id in _visible_ids(session_b)

    flag_manual_transaction(session_a, row_a.id)
    _sync(session_a, session_b, path_b, tmp_path / "from_a_second")

    stored = session_b.get(Transaction, row_a.id)
    assert stored is not None, "the flag removes the row from the list, not from the table"
    assert stored.deleted_at is not None
    assert row_a.id not in _visible_ids(session_b)


def test_a_snapshot_with_an_imported_row_of_the_pseudo_account_is_refused(
    device_a, tmp_path
):
    """Only a hand-entered row belongs to the pseudo account.

    A snapshot carries the hand-entered rows between the devices. A row of the
    account `CASH` that is not hand-entered is not correct, so `read_snapshot`
    refuses the complete file before the import makes a change.
    """
    import gzip
    import json

    from abn_combined.core.snapshots import SnapshotError

    session_a, _path_a = device_a
    create_manual_transaction(
        session_a,
        transactiondate=date(2026, 3, 6),
        amount=-3.00,
        description="Water",
    )
    path = export_snapshot(session_a, tmp_path / "from_a")
    payload = json.loads(gzip.decompress(path.read_bytes()))
    payload["transactions"][0]["is_manual"] = False
    blob = gzip.compress(json.dumps(payload).encode("utf-8"))

    with pytest.raises(SnapshotError, match="reserved account"):
        read_snapshot(blob)
