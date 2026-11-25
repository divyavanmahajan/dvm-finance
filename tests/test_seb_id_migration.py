"""The Alembic migration f5c3a8e2b710 changes each stored SEB id to the SEB voucher key."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import abn_combined.parsers.seb as seb_mod
from abn_combined.core.importer import import_file
from abn_combined.migrations import _alembic_config
from abn_combined.settings import Settings
from alembic import command

FIXTURES = Path(__file__).parent / "fixtures"
SEB_SAMPLE = FIXTURES / "seb_sample.csv"
ACCOUNT = "seb:divyavanmahajan"
BEFORE = "e4b7d2a91c36"
REVISION = "f5c3a8e2b710"


@pytest.fixture
def old_db(tmp_path):
    """A database at the revision before the migration."""
    settings = Settings.create(data_dir=tmp_path / "data")
    settings.ensure_data_dir()
    command.upgrade(_alembic_config(settings), BEFORE)
    return settings


def _insert(conn, trans_id, booking_date, amount, balance, voucher="5400000001", **extra):
    structured = {
        "format": "seb", "voucher_number": voucher, "native_amount": amount,
        "native_currency": "SEK", "native_balance": balance, "eur_rate_used": 11.29,
    }
    row = {
        "id": trans_id, "accountNumber": ACCOUNT, "transactiondate": booking_date,
        "valuedate": booking_date, "amount": round(amount / 11.29, 2), "currency": "EUR",
        "description": "CARD", "description_structured": json.dumps(structured),
        "is_manual": 0,
    }
    row.update(extra)
    cols = ", ".join(row)
    marks = ", ".join(f":{c}" for c in row)
    conn.execute(f"INSERT INTO transactions ({cols}) VALUES ({marks})", row)


def _connect(settings):
    return sqlite3.connect(settings.db_path)


def test_upgrade_changes_the_ids_and_keeps_the_references(old_db):
    old = f"{ACCOUNT}_5400000001"
    with _connect(old_db) as conn:
        _insert(conn, old, "2026-10-02", -412.3, 1234.56,
                manual_category="groceries", manual_tags="weekly")
        _insert(conn, f"{ACCOUNT}_5490990789", "2026-10-03", -50.0, None,
                voucher="5490990789", merged_into=old, deleted_at="2026-11-01 00:00:00")
        conn.execute("INSERT INTO rule_change_reports (id, created_at, action) "
                     "VALUES (1, '2026-11-01 00:00:00', 'recategorize')")
        conn.execute("INSERT INTO rule_change_items (report_id, transaction_id) VALUES (1, ?)",
                     (old,))
        # A row without a voucher number keeps its generic id.
        conn.execute(
            "INSERT INTO transactions (id, accountNumber, transactiondate, amount, currency, "
            "description_structured, is_manual) VALUES ('seb:divyavanmahajan_2026-10-04_-1.0_abc', "
            "?, '2026-10-04', -1.0, 'EUR', '{}', 0)", (ACCOUNT,))

    command.upgrade(_alembic_config(old_db), "head")

    new = f"{ACCOUNT}_5400000001_2026-10-02_-412.30_1234.56"
    with _connect(old_db) as conn:
        ids = {r[0] for r in conn.execute("SELECT id FROM transactions")}
        assert ids == {new, f"{ACCOUNT}_5490990789_2026-10-03_-50.00_",
                       "seb:divyavanmahajan_2026-10-04_-1.0_abc"}
        assert conn.execute(
            "SELECT manual_category, manual_tags FROM transactions WHERE id = ?", (new,)
        ).fetchone() == ("groceries", "weekly")
        assert conn.execute(
            "SELECT merged_into FROM transactions WHERE id LIKE ?", (f"{ACCOUNT}_5490990789%",)
        ).fetchone() == (new,)
        assert conn.execute("SELECT transaction_id FROM rule_change_items").fetchone() == (new,)

    backups = list(old_db.data_dir.glob("abn_combined.db.before-seb-ids-*"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as copy:
        assert copy.execute("SELECT id FROM transactions WHERE manual_category IS NOT NULL"
                            ).fetchone() == (old,)


def test_upgrade_without_old_ids_makes_no_backup(old_db):
    command.upgrade(_alembic_config(old_db), "head")
    assert not list(old_db.data_dir.glob("abn_combined.db.before-seb-ids-*"))


def test_downgrade_restores_the_old_ids(old_db):
    with _connect(old_db) as conn:
        _insert(conn, f"{ACCOUNT}_5400000001", "2026-10-02", -412.3, 1234.56)
    cfg = _alembic_config(old_db)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, BEFORE)
    with _connect(old_db) as conn:
        assert [r[0] for r in conn.execute("SELECT id FROM transactions")] == [
            f"{ACCOUNT}_5400000001"
        ]


def test_downgrade_refuses_two_rows_with_one_voucher(old_db):
    cfg = _alembic_config(old_db)
    command.upgrade(cfg, "head")
    with _connect(old_db) as conn:
        _insert(conn, f"{ACCOUNT}_5400000001_2026-10-19_-149.00_3100.25",
                "2026-10-19", -149.0, 3100.25)
        _insert(conn, f"{ACCOUNT}_5400000001_2026-10-19_-149.00_2200.75",
                "2026-10-19", -149.0, 2200.75)
    with pytest.raises(RuntimeError, match="Cannot downgrade"):
        command.downgrade(cfg, BEFORE)


def test_import_of_the_latest_file_after_the_migration(old_db, monkeypatch):
    """The old import kept one row for each voucher number. The new import adds the rest."""
    from abn_combined.app import create_app
    from abn_combined.db import get_session_factory

    monkeypatch.setattr(seb_mod, "_build_rate_cache", lambda dates: {d: 11.29 for d in dates})
    parsed = seb_mod.parse_seb_file(SEB_SAMPLE)
    stored: dict[str, dict] = {}
    for trans in parsed:
        stored.setdefault(trans["seb_voucher_id"], trans)
    with _connect(old_db) as conn:
        for voucher, trans in stored.items():
            structured = json.loads(trans["description_structured"])
            _insert(conn, f"{ACCOUNT}_{voucher}", trans["transactiondate"].isoformat(),
                    structured["native_amount"], structured["native_balance"], voucher=voucher)

    create_app(old_db)
    command.upgrade(_alembic_config(old_db), "head")
    with get_session_factory()() as db:
        summary = import_file(db, SEB_SAMPLE.read_bytes(), SEB_SAMPLE.name,
                              old_db.statements_dir, fmt="seb")
    assert len(stored) < len(parsed)
    assert (summary.new, summary.duplicates, summary.corrected) == (
        len(parsed) - len(stored), len(stored), 0
    )
