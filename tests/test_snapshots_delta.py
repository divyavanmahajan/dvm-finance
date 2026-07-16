"""Delta-snapshot export/import tests.

A delta snapshot carries only the transactions changed since a ``since``
boundary (``updated_at >= since``), plus a self-describing header
(``delta: true``, ``since: <iso>``). The import path is the same incoming-wins
merge as a full snapshot; these tests verify the delta filter, the export-state
marker, header provenance surfaced on the import report, and that a delta with
fewer transactions merges without touching absent local rows.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from abn_combined.core.models import Base, ExportState, SnapshotImport, Transaction
from abn_combined.core.snapshots import (
    build_snapshot,
    export_snapshot,
    get_last_delta_export_at,
    import_snapshot,
    read_snapshot,
)


def _make_db(tmp_path: Path, name: str) -> tuple[Session, Path]:
    data_dir = tmp_path / name
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "abn_combined.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)(), db_path


def _txn(txn_id: str, updated_at: datetime | None, **kw) -> Transaction:
    defaults = dict(
        id=txn_id,
        accountNumber="NL01TEST0123456789",
        transactiondate=date(2026, 1, 15),
        amount=Decimal("-10.00"),
        description=f"payment {txn_id}",
        currency="EUR",
        updated_at=updated_at,
    )
    defaults.update(kw)
    return Transaction(**defaults)


def test_build_snapshot_delta_filters_by_updated_at(tmp_path):
    db, _ = _make_db(tmp_path, "a")
    since = datetime(2026, 6, 1, 12, 0, 0)
    # Before `since`, on the boundary, after `since`, and never-touched (NULL).
    db.add(_txn("before", since - timedelta(hours=1)))
    db.add(_txn("boundary", since))
    db.add(_txn("after", since + timedelta(hours=1)))
    db.add(_txn("never", None))
    db.commit()

    payload = build_snapshot(db, machine_id="m", since=since)

    ids = {t["id"] for t in payload["transactions"]}
    assert ids == {"boundary", "after"}, "edits at/after `since` included; before & NULL excluded"
    assert payload["header"]["delta"] is True
    assert payload["header"]["since"] == since.isoformat(timespec="seconds")


def test_build_snapshot_full_has_no_delta_header(tmp_path):
    db, _ = _make_db(tmp_path, "a")
    db.add(_txn("t1", datetime(2026, 6, 1)))
    db.commit()
    payload = build_snapshot(db, machine_id="m")
    assert "delta" not in payload["header"]
    assert "since" not in payload["header"]
    assert {t["id"] for t in payload["transactions"]} == {"t1"}


def test_export_delta_advances_export_state_marker(tmp_path):
    db, _ = _make_db(tmp_path, "a")
    db.add(_txn("t1", datetime(2026, 6, 1)))
    db.commit()

    assert get_last_delta_export_at(db) is None
    before = datetime.now()
    path = export_snapshot(db, tmp_path / "a", since=datetime(2026, 1, 1))
    assert path.name.startswith("delta-")

    marker = get_last_delta_export_at(db)
    assert marker is not None and marker >= before
    # Exactly one export_state row is ever created.
    assert db.query(ExportState).count() == 1


def test_delta_roundtrip_only_recent_edits_reach_target(tmp_path):
    """Edits after `since` appear in the delta; edits before do not; and the
    target keeps local rows absent from the delta (incoming-wins-per-present)."""
    source, _ = _make_db(tmp_path, "source")
    since = datetime(2026, 6, 1, 12, 0, 0)
    source.add(_txn("old", since - timedelta(days=1), category="groceries"))
    source.add(_txn("recent", since + timedelta(days=1), category="dining"))
    source.commit()

    payload = build_snapshot(source, machine_id="src", since=since)
    assert {t["id"] for t in payload["transactions"]} == {"recent"}

    # Target already has `old` (a different category) plus a local-only `t_local`.
    target, target_path = _make_db(tmp_path, "target")
    target.add(_txn("old", since - timedelta(days=1), category="OLD-LOCAL"))
    target.add(_txn("t_local", since, category="keep-me"))
    target.commit()

    import_snapshot(target, payload, target_path)

    # `recent` inserted; `old` untouched (not in delta); `t_local` preserved.
    assert target.get(Transaction, "recent").category == "dining"
    assert target.get(Transaction, "old").category == "OLD-LOCAL"
    assert target.get(Transaction, "t_local").category == "keep-me"


def test_import_records_delta_provenance(tmp_path):
    source, _ = _make_db(tmp_path, "source")
    since = datetime(2026, 6, 1, 12, 0, 0)
    source.add(_txn("recent", since + timedelta(days=1)))
    source.commit()
    payload = build_snapshot(source, machine_id="src", since=since)

    target, target_path = _make_db(tmp_path, "target")
    result = import_snapshot(target, payload, target_path)

    stored = target.get(SnapshotImport, result.id)
    assert stored.is_delta is True
    assert stored.delta_since == since


def test_import_full_snapshot_is_not_delta(tmp_path):
    source, _ = _make_db(tmp_path, "source")
    source.add(_txn("t1", datetime(2026, 6, 1)))
    source.commit()
    payload = build_snapshot(source, machine_id="src")

    target, target_path = _make_db(tmp_path, "target")
    result = import_snapshot(target, payload, target_path)
    assert target.get(SnapshotImport, result.id).is_delta is False


def test_delta_file_reads_back_as_valid_snapshot(tmp_path):
    db, _ = _make_db(tmp_path, "a")
    db.add(_txn("t1", datetime(2026, 6, 2)))
    db.commit()
    path = export_snapshot(db, tmp_path / "a", since=datetime(2026, 1, 1))
    payload = read_snapshot(path.read_bytes())
    assert payload["header"]["delta"] is True
    assert isinstance(payload["transactions"], list)


def test_manual_and_rule_writes_stamp_updated_at(tmp_path):
    """apply_rules stamps updated_at so rule-driven changes land in deltas."""
    from abn_combined.core.categorizer import apply_rules
    from abn_combined.core.models import CategorizationRule

    db, _ = _make_db(tmp_path, "a")
    db.add(CategorizationRule(
        uuid="00000000-0000-0000-0000-000000000001",
        priority=100, rule_type="full_description", match_pattern="contains",
        field_target="description", match_value="payment", category="dining",
        is_active=True,
    ))
    db.add(_txn("t1", None))
    db.commit()

    apply_rules(db)
    assert db.get(Transaction, "t1").updated_at is not None
