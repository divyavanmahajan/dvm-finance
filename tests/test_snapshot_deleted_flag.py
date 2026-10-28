"""The two surfaces that still read a flagged transaction (3.6), and the
snapshot round trip of the flag (4.1, 4.2).

A snapshot export holds a flagged transaction with its flag, so that the flag
reaches each other machine. The duplicate check treats the id of a flagged
transaction as taken, so that no second row claims it. Neither surface uses the
shared `live_only` predicate.

The round trip needs `deleted_at` in `_TXN_DATETIME_COLUMNS` in
`core/snapshots.py`. Without it, an import gives the column a text value, and
SQLite refuses the write.
"""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from abn_combined.core.budget_report import compute_actual
from abn_combined.core.cash_flow import compute_cash_flow
from abn_combined.core.dedup import check_duplicates
from abn_combined.core.filters import TransactionFilter, paginate
from abn_combined.core.models import Base, Transaction
from abn_combined.core.snapshots import (
    build_snapshot,
    export_snapshot,
    import_snapshot,
    read_snapshot,
)
from abn_combined.core.trends import TrendsParams, aggregate

WINDOW_FROM = date(2026, 3, 1)
WINDOW_TO = date(2026, 3, 31)
TXN_DATE = date(2026, 3, 10)
FLAG_TIME = datetime(2026, 3, 20, 9, 30, 0)
FLAGGED_ID = "manual-flagged-1"


def _make_db(tmp_path: Path, name: str) -> tuple[Session, Path]:
    data_dir = tmp_path / name
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "abn_combined.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)(), db_path


@pytest.fixture
def db_a(tmp_path):
    session, db_path = _make_db(tmp_path, "machine_a")
    yield session, db_path
    session.close()


@pytest.fixture
def db_b(tmp_path):
    session, db_path = _make_db(tmp_path, "machine_b")
    yield session, db_path
    session.close()


def _flagged_row() -> Transaction:
    """One hand-entered transaction that the user flagged for removal."""
    return Transaction(
        id=FLAGGED_ID,
        accountNumber="CASH",
        transactiondate=TXN_DATE,
        amount=-20.0,
        currency="EUR",
        description="Cash lunch",
        manual_category="food",
        manual_tags="lunch",
        is_manual=True,
        deleted_at=FLAG_TIME,
    )


def _is_invisible(db: Session) -> None:
    """Assert that each reader of a total holds no row."""
    page = paginate(db, TransactionFilter(date_from=WINDOW_FROM, date_to=WINDOW_TO))
    assert page.total == 0
    assert aggregate(db, TrendsParams(date_from=WINDOW_FROM, date_to=WINDOW_TO)).grand_total == 0
    result = compute_cash_flow(db, WINDOW_FROM, WINDOW_TO)
    assert result.total_expense == 0.0
    assert result.total_income == 0.0
    assert compute_actual(db, "food", WINDOW_FROM, WINDOW_TO) == 0.0


# ---------------------------------------------------------------------------
# 3.6 The two surfaces that still read a flagged row
# ---------------------------------------------------------------------------


def test_the_snapshot_export_holds_a_flagged_row_with_its_flag(db_a):
    """The export never hides a flagged row, so the flag reaches each machine."""
    db, _db_path = db_a
    db.add(_flagged_row())
    db.commit()

    payload = build_snapshot(db, machine_id="machine-a")
    rows = {t["id"]: t for t in payload["transactions"]}
    assert FLAGGED_ID in rows
    assert rows[FLAGGED_ID]["deleted_at"] == FLAG_TIME.isoformat()
    assert rows[FLAGGED_ID]["is_manual"] is True


def test_the_exported_file_holds_the_flag(db_a, tmp_path):
    """The written file holds the flag, not only the payload in memory."""
    db, _db_path = db_a
    db.add(_flagged_row())
    db.commit()

    path = export_snapshot(db, tmp_path / "exports")
    payload = read_snapshot(path.read_bytes())
    rows = {t["id"]: t for t in payload["transactions"]}
    assert rows[FLAGGED_ID]["deleted_at"] == FLAG_TIME.isoformat()


def test_the_duplicate_check_treats_the_id_of_a_flagged_row_as_taken(db_a):
    """A second row cannot claim the id of a flagged row."""
    db, _db_path = db_a
    incoming = {
        "accountNumber": "NL01",
        "transactiondate": TXN_DATE,
        "amount": -20.0,
        "description": "Card payment",
    }
    # Give the flagged row the exact id that the duplicate check computes.
    from abn_combined.core.dedup import generate_transaction_id

    taken_id = generate_transaction_id(incoming)
    row = _flagged_row()
    row.id = taken_id
    db.add(row)
    db.commit()

    new, duplicates = check_duplicates(db, [dict(incoming)])
    assert new == []
    assert len(duplicates) == 1


# ---------------------------------------------------------------------------
# 4.1 and 4.2 The round trip of the flag
# ---------------------------------------------------------------------------


def test_the_flag_travels_to_a_second_machine(db_a, db_b, tmp_path):
    """Export a flagged row on machine A. Import the file on machine B."""
    session_a, _path_a = db_a
    session_b, path_b = db_b
    session_a.add(_flagged_row())
    session_a.commit()

    path = export_snapshot(session_a, tmp_path / "machine_a")
    payload = read_snapshot(path.read_bytes())
    import_snapshot(session_b, payload, path_b)

    row = session_b.get(Transaction, FLAGGED_ID)
    assert row is not None
    assert row.is_manual is True
    assert row.deleted_at == FLAG_TIME
    _is_invisible(session_b)


def test_a_purged_row_returns_flagged_and_invisible(db_a, db_b, tmp_path):
    """Machine A deletes the row. A later snapshot from machine B returns it.

    The row returns with its flag, so it stays out of each list and each total.
    A purge therefore needs no tombstone, and the return of a row is harmless.
    """
    session_a, path_a = db_a
    session_b, path_b = db_b

    # Machine A holds the flagged row. Machine B receives it.
    session_a.add(_flagged_row())
    session_a.commit()
    first = export_snapshot(session_a, tmp_path / "machine_a")
    import_snapshot(session_b, read_snapshot(first.read_bytes()), path_b)
    assert session_b.get(Transaction, FLAGGED_ID) is not None

    # Machine A purges the row. The purge deletes the row from the database.
    session_a.delete(session_a.get(Transaction, FLAGGED_ID))
    session_a.commit()
    assert session_a.get(Transaction, FLAGGED_ID) is None

    # Machine B still holds the row, and it exports the row with its flag.
    second = export_snapshot(session_b, tmp_path / "machine_b")
    import_snapshot(session_a, read_snapshot(second.read_bytes()), path_a)

    row = session_a.get(Transaction, FLAGGED_ID)
    assert row is not None
    assert row.deleted_at == FLAG_TIME
    _is_invisible(session_a)


def test_the_export_payload_of_a_second_machine_names_the_flag(db_b, tmp_path):
    """A machine that keeps the row exports the flag in the written file.

    This check reads the raw JSON. It proves that the second machine carries
    the flag that returns the row to a machine that purged it.
    """
    session_b, _path_b = db_b
    session_b.add(_flagged_row())
    session_b.commit()
    path = export_snapshot(session_b, tmp_path / "machine_b")
    blob = gzip.decompress(path.read_bytes())
    payload = json.loads(blob)
    rows = {t["id"]: t for t in payload["transactions"]}
    assert rows[FLAGGED_ID]["deleted_at"] == FLAG_TIME.isoformat()
