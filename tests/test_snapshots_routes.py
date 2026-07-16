"""Route tests for the Snapshots page: export download, listing, import, reports."""

from __future__ import annotations

import gzip
import json
from datetime import date
from decimal import Decimal

import pytest

from abn_combined.core.models import SnapshotImport, Transaction
from abn_combined.core.snapshots import SCHEMA_VERSION
from abn_combined.db import get_session_factory


@pytest.fixture
def db(client):
    session = get_session_factory()()
    yield session
    session.close()


def _seed_txn(db, txn_id="t1", **kw):
    defaults = dict(
        id=txn_id,
        accountNumber="NL01TEST0123456789",
        transactiondate=date(2026, 1, 15),
        amount=Decimal("-10.00"),
        description=f"Payment {txn_id}",
        currency="EUR",
    )
    defaults.update(kw)
    db.add(Transaction(**defaults))
    db.commit()


def test_snapshots_page_renders(client):
    resp = client.get("/snapshots")
    assert resp.status_code == 200
    assert "Export" in resp.text
    assert "Import" in resp.text


def test_export_returns_download_and_lists_file(client, settings, db):
    _seed_txn(db)
    resp = client.post("/snapshots/export")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    payload = json.loads(gzip.decompress(resp.content))
    assert payload["header"]["schema_version"] == SCHEMA_VERSION
    assert len(payload["transactions"]) == 1

    # File persisted to <data_dir>/snapshots/ and listed on the page.
    files = list(settings.snapshots_dir.glob("*.json.gz"))
    assert len(files) == 1
    page = client.get("/snapshots")
    assert files[0].name in page.text


def test_past_export_download_link(client, settings, db):
    client.post("/snapshots/export")
    (path,) = list(settings.snapshots_dir.glob("*.json.gz"))
    resp = client.get(f"/snapshots/files/{path.name}")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]


def test_download_rejects_unknown_and_traversal_names(client):
    assert client.get("/snapshots/files/nope.json.gz").status_code == 404
    assert client.get("/snapshots/files/..%2Fabn_combined.db").status_code == 404


def test_import_round_trip_shows_report(client, settings, db):
    _seed_txn(db, "t1", category="groceries")
    export = client.post("/snapshots/export")

    # Change local state so the import overwrites it (incoming wins).
    txn = db.get(Transaction, "t1")
    txn.manual_category = "dining"
    db.commit()

    resp = client.post(
        "/snapshots/import",
        files={"file": ("snap.json.gz", export.content, "application/gzip")},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    page = client.get(resp.headers["location"])
    assert page.status_code == 200
    assert "Import report" in page.text

    db.expire_all()
    assert db.get(Transaction, "t1").manual_category is None  # incoming won
    stored = db.query(SnapshotImport).one()
    assert stored.counts["transactions"]["updated"] == 1
    # Backup was created in the data dir.
    assert list(settings.data_dir.glob("*.backup-*.db"))


def test_import_report_renders_in_rules_history(client, db):
    _seed_txn(db, "t1", category="groceries")
    export = client.post("/snapshots/export")
    txn = db.get(Transaction, "t1")
    txn.category = "other"
    db.commit()

    client.post(
        "/snapshots/import",
        files={"file": ("snap.json.gz", export.content, "application/gzip")},
    )
    history = client.get("/rules/history")
    assert history.status_code == 200
    assert "action-import" in history.text


def test_import_rejects_schema_version_mismatch(client):
    payload = {
        "header": {"schema_version": 99, "exported_at": "x", "machine_id": "m"},
        "transactions": [], "rules": [], "budgets": [], "rule_change_reports": [],
    }
    blob = gzip.compress(json.dumps(payload).encode())
    resp = client.post(
        "/snapshots/import",
        files={"file": ("snap.json.gz", blob, "application/gzip")},
    )
    assert resp.status_code == 400
    assert "Schema version mismatch" in resp.text


def test_import_rejects_corrupt_file(client, db):
    resp = client.post(
        "/snapshots/import",
        files={"file": ("snap.json.gz", b"garbage bytes", "application/gzip")},
    )
    assert resp.status_code == 400
    assert "Not a valid snapshot file" in resp.text
    # Nothing was recorded for a rejected file.
    assert db.query(SnapshotImport).count() == 0


def test_export_delta_downloads_filtered_snapshot(client, settings, db):
    from datetime import datetime, timedelta

    since = datetime(2026, 6, 1, 12, 0, 0)
    _seed_txn(db, "old", updated_at=since - timedelta(days=1))
    _seed_txn(db, "recent", updated_at=since + timedelta(hours=1))

    resp = client.post("/snapshots/export-delta", data={"since": since.isoformat()})
    assert resp.status_code == 200
    payload = json.loads(gzip.decompress(resp.content))
    assert payload["header"]["delta"] is True
    assert {t["id"] for t in payload["transactions"]} == {"recent"}

    # Delta file persisted with a delta- prefix and listed on the page.
    files = list(settings.snapshots_dir.glob("delta-*.json.gz"))
    assert len(files) == 1


def test_export_delta_defaults_to_last_marker(client, settings, db):
    from datetime import datetime

    _seed_txn(db, "t1", updated_at=datetime(2026, 6, 5))
    # First delta with an explicit early boundary sets the marker.
    client.post("/snapshots/export-delta", data={"since": datetime(2026, 1, 1).isoformat()})
    page = client.get("/snapshots")
    assert "Defaults to your last delta export" in page.text
