"""Import pipeline + upload API tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from abn_combined.core.importer import ImportError_, import_file
from abn_combined.core.models import CategorizationRule
from abn_combined.db import get_session_factory

FIXTURES = Path(__file__).parent / "fixtures"

PAYPAL = FIXTURES / "paypal_sample.TXT"
WISE = FIXTURES / "wise_sample.csv"
SEB = FIXTURES / "seb_sample.csv"
MT940 = FIXTURES / "mt940_sample.STA"


def _db(app):
    return get_session_factory()()


# --- import_file (unit over the pipeline) --------------------------------

@pytest.mark.parametrize(
    "fixture,fmt",
    [(PAYPAL, "paypal"), (WISE, "wise"), (SEB, "seb"), (MT940, "auto")],
)
def test_import_each_format(app, settings, fixture, fmt):
    db = _db(app)
    try:
        summary = import_file(
            db, fixture.read_bytes(), fixture.name, settings.statements_dir, fmt=fmt
        )
        assert summary.new > 0
        assert summary.source_file == fixture.name
        # File was stored under statements/.
        assert any(settings.statements_dir.glob(f"*_{fixture.name}"))
    finally:
        db.close()


def test_reimport_is_all_duplicates(app, settings):
    db = _db(app)
    try:
        first = import_file(db, MT940.read_bytes(), MT940.name, settings.statements_dir)
        assert first.new > 0
        second = import_file(db, MT940.read_bytes(), MT940.name, settings.statements_dir)
        assert second.new == 0
        # Every parsed row is now a duplicate (DB rows + in-batch repeats).
        assert second.duplicates == first.new + first.duplicates
    finally:
        db.close()


def test_import_applies_rules(app, settings):
    db = _db(app)
    try:
        db.add(
            CategorizationRule(
                rule_type="keyword",
                match_pattern="contains",
                field_target="description",
                match_value="kinoheld",
                category="entertainment",
            )
        )
        db.commit()
        summary = import_file(
            db, PAYPAL.read_bytes(), PAYPAL.name, settings.statements_dir, fmt="paypal"
        )
        assert summary.categorized > 0
    finally:
        db.close()


def test_import_bad_file_raises(app, settings):
    db = _db(app)
    try:
        with pytest.raises(ImportError_):
            import_file(db, b"not a statement", "junk.mt940", settings.statements_dir)
    finally:
        db.close()


def test_import_unknown_format_raises(app, settings):
    db = _db(app)
    try:
        with pytest.raises(ImportError_):
            import_file(db, b"x", "f.csv", settings.statements_dir, fmt="nope")
    finally:
        db.close()


# --- API -----------------------------------------------------------------

def test_upload_page_renders(client):
    resp = client.get("/upload")
    assert resp.status_code == 200
    assert "Upload a statement" in resp.text


def test_api_upload_json_summary(client):
    resp = client.post(
        "/api/upload",
        files={"file": (MT940.name, MT940.read_bytes(), "application/octet-stream")},
        data={"format": "auto"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["new"] > 0
    assert body["source_file"] == MT940.name


def test_api_upload_htmx_partial(client):
    resp = client.post(
        "/api/upload",
        files={"file": (PAYPAL.name, PAYPAL.read_bytes(), "application/octet-stream")},
        data={"format": "paypal"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "Imported" in resp.text
    assert "new transactions" in resp.text


def test_api_upload_duplicate_reupload(client):
    files = {"file": (MT940.name, MT940.read_bytes(), "application/octet-stream")}
    first = client.post("/api/upload", files=files, data={"format": "auto"})
    assert first.json()["new"] > 0
    second = client.post(
        "/api/upload",
        files={"file": (MT940.name, MT940.read_bytes(), "application/octet-stream")},
        data={"format": "auto"},
    )
    assert second.json()["new"] == 0
    assert second.json()["duplicates"] > 0


def test_api_upload_bad_file_422(client):
    resp = client.post(
        "/api/upload",
        files={"file": ("junk.mt940", b"garbage", "application/octet-stream")},
        data={"format": "auto"},
    )
    assert resp.status_code == 422
    assert "No transactions" in resp.json()["detail"] or "Could not parse" in resp.json()["detail"]


def test_api_upload_invalid_format_422(client):
    resp = client.post(
        "/api/upload",
        files={"file": (MT940.name, MT940.read_bytes(), "application/octet-stream")},
        data={"format": "bogus"},
    )
    assert resp.status_code == 422
