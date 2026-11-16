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
FTFCU = FIXTURES / "ftfcu_sample.ofx"


def _db(app):
    return get_session_factory()()


# --- import_file (unit over the pipeline) --------------------------------

@pytest.mark.parametrize(
    "fixture,fmt",
    [(PAYPAL, "paypal"), (WISE, "wise"), (SEB, "seb"), (FTFCU, "ftfcu"), (MT940, "auto")],
)
def test_import_each_format(app, settings, fixture, fmt, monkeypatch):
    # Keep the EUR conversion offline (SEB and First Tech fetch ECB rates).
    import abn_combined.parsers.ftfcu as ftfcu_mod

    monkeypatch.setattr(ftfcu_mod, "build_rate_cache", lambda dates, currency: {})
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
                match_value="fcgiavzz",
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
    resp = client.get("/import")
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


# --- Correction of a stored amount (paypal-amount-decimal-separator) -------

PAYPAL_PERIOD = FIXTURES / "paypal_period_decimal.TXT"


def _import(db, settings, path=PAYPAL_PERIOD, fmt="paypal"):
    return import_file(db, path.read_bytes(), path.name, settings.statements_dir, fmt=fmt)


def _row(db, paypal_id):
    from abn_combined.core.models import Transaction

    return db.query(Transaction).filter(Transaction.id.endswith("_" + paypal_id)).one()


def _break_amount(db, paypal_id, amount):
    """Store a wrong amount, as the old parser did for a period-decimal report."""
    from datetime import datetime

    from abn_combined.core.utils import calculate_transaction_hash_components

    row = _row(db, paypal_id)
    row.amount = amount
    row.transaction_hash = calculate_transaction_hash_components(
        date_value=row.transactiondate, description=row.description,
        amount=amount, account=row.accountNumber,
    )
    row.updated_at = datetime(2000, 1, 1)
    db.commit()
    return row.transaction_hash


def test_reimport_corrects_a_changed_amount(app, settings):
    db = _db(app)
    try:
        first = _import(db, settings)
        old_hash = _break_amount(db, "TESTDOT0000000001", -1234)
        row = _row(db, "TESTDOT0000000001")
        row.manual_category = "shopping"
        row.manual_tags = "gift"
        db.commit()

        summary = _import(db, settings)

        assert summary.new == 0
        assert summary.corrected == 1
        assert summary.duplicates == first.new + first.duplicates - 1
        [correction] = summary.corrections
        assert correction["id"] == row.id
        assert correction["old_amount"] == -1234
        assert correction["new_amount"] == pytest.approx(-12.34)

        db.expire_all()
        row = _row(db, "TESTDOT0000000001")
        assert float(row.amount) == pytest.approx(-12.34)
        assert (row.manual_category, row.manual_tags) == ("shopping", "gift")
        assert row.updated_at.year > 2000
        assert row.transaction_hash != old_hash
    finally:
        db.close()


def test_reimport_with_equal_amounts_corrects_nothing(app, settings):
    db = _db(app)
    try:
        first = _import(db, settings)
        second = _import(db, settings)
        assert second.corrected == 0
        assert second.corrections == []
        assert second.duplicates == first.new + first.duplicates
    finally:
        db.close()


def test_reimport_does_not_correct_a_flagged_row(app, settings):
    from datetime import datetime

    db = _db(app)
    try:
        _import(db, settings)
        _break_amount(db, "TESTDOT0000000001", -1234)
        row = _row(db, "TESTDOT0000000001")
        row.deleted_at = datetime(2026, 1, 1)
        db.commit()

        summary = _import(db, settings)

        assert summary.corrected == 0
        db.expire_all()
        assert float(_row(db, "TESTDOT0000000001").amount) == -1234
    finally:
        db.close()


def test_correct_amounts_skips_a_duplicate_with_another_id(app, settings):
    """A duplicate found by the reference or the counterparty has another id."""
    from datetime import date

    from abn_combined.core.importer import correct_amounts

    db = _db(app)
    try:
        _import(db, settings)
        stored = _row(db, "TESTDOT0000000001")
        duplicate = {
            "accountNumber": stored.accountNumber,
            "transactiondate": date(2026, 3, 2),
            "amount": -99.0,
            "description": "another form of the same payment",
        }
        assert correct_amounts(db, [duplicate]) == []
        db.expire_all()
        assert float(_row(db, "TESTDOT0000000001").amount) == pytest.approx(-12.34)
    finally:
        db.close()


def test_correct_amounts_handles_each_id_once(app, settings):
    """Two incoming rows with one id correct the stored row only once."""
    from abn_combined.core.importer import correct_amounts
    from abn_combined.parsers.paypal import parse_paypal_file

    db = _db(app)
    try:
        _import(db, settings)
        _break_amount(db, "TESTDOT0000000001", -1234)
        [incoming] = [t for t in parse_paypal_file(PAYPAL_PERIOD)
                      if t["paypal_transaction_id"] == "TESTDOT0000000001"]
        corrections = correct_amounts(db, [incoming, dict(incoming, amount=-1.0)])
        assert [c["new_amount"] for c in corrections] == [pytest.approx(-12.34)]
    finally:
        db.close()


def _break_via_client(app, paypal_id, amount):
    db = _db(app)
    try:
        _break_amount(db, paypal_id, amount)
    finally:
        db.close()


def _upload_period(client, **headers):
    return client.post(
        "/api/upload",
        files={"file": (PAYPAL_PERIOD.name, PAYPAL_PERIOD.read_bytes(),
                        "application/octet-stream")},
        data={"format": "paypal"},
        headers=headers,
    )


def test_api_upload_json_reports_corrections(client, app):
    assert _upload_period(client).json()["new"] > 0
    _break_via_client(app, "TESTDOT0000000001", -1234)
    body = _upload_period(client).json()
    assert body["corrected"] == 1
    [correction] = body["corrections"]
    assert correction["id"].endswith("_TESTDOT0000000001")
    assert correction["old_amount"] == -1234
    assert correction["new_amount"] == pytest.approx(-12.34)


def test_api_upload_htmx_partial_lists_corrections(client, app):
    _upload_period(client)
    _break_via_client(app, "TESTDOT0000000001", -1234)
    resp = _upload_period(client, **{"HX-Request": "true"})
    assert "<strong>1</strong> amounts corrected" in resp.text
    assert "-1234.00" in resp.text and "-12.34" in resp.text


def test_api_upload_htmx_partial_hides_corrections_when_none(client):
    resp = _upload_period(client, **{"HX-Request": "true"})
    assert "amounts corrected" not in resp.text
