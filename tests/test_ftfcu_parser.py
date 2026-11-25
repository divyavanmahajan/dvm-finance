"""Tests for the First Tech Federal Credit Union OFX parser and the ECB rate helpers.

The fixture is synthetic: the account numbers are fake. The tests replace the
ECB fetch, so they run offline and assert the exact EUR conversion.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import abn_combined.parsers.ftfcu as ftfcu_mod
from abn_combined.parsers import fx
from abn_combined.parsers.ftfcu import normalize_fitid, parse_ftfcu_file

FIXTURE = Path(__file__).parent / "fixtures" / "ftfcu_sample.ofx"

# EUR→USD: 1 EUR = 1.25 USD on 2026-11-02 and 1.10 USD on 2026-10-16.
RATES = {date(2026, 10, 16): 1.10, date(2026, 11, 2): 1.25}


@pytest.fixture
def fixed_rates(monkeypatch):
    calls: list[tuple] = []

    def _fake_cache(dates, currency):
        calls.append((sorted(set(dates)), currency))
        return dict(RATES)

    monkeypatch.setattr(ftfcu_mod, "build_rate_cache", _fake_cache)
    return calls


@pytest.fixture
def no_rates(monkeypatch):
    monkeypatch.setattr(ftfcu_mod, "build_rate_cache", lambda dates, currency: {})


def _by_fitid(txns):
    return {t["ftfcu_fitid"]: t for t in txns}


def test_parse_all_accounts_including_creditline(fixed_rates):
    txns = parse_ftfcu_file(FIXTURE)
    # 1 savings + 3 checking + 0 empty savings + 1 card.
    assert len(txns) == 5
    assert {t["accountNumber"] for t in txns} == {"ftfcu:0001", "ftfcu:0002", "ftfcu:9999"}
    card = _by_fitid(txns)["20261110-100005-2500-12"]
    assert json.loads(card["description_structured"])["account_type"] == "CREDITLINE"
    assert fixed_rates == [(sorted({t["transactiondate"] for t in txns}), "USD")]


def test_full_account_number_is_never_stored(fixed_rates):
    txns = parse_ftfcu_file(FIXTURE)
    blob = json.dumps(txns, default=str)
    for full in ("4000123412349999", "11110001", "11110002"):
        assert full not in blob


def test_fitid_normalized_for_identity_and_raw_kept(fixed_rates):
    txn = _by_fitid(parse_ftfcu_file(FIXTURE))["20261113-100002-1049-7693"]
    assert txn["transaction_reference"] == "20261113 100002 1,049 7,693"
    structured = json.loads(txn["description_structured"])
    assert structured["fitid"] == "20261113 100002 1,049 7,693"


def test_normalize_fitid():
    assert normalize_fitid("20261105 100002 123,456 7,650") == "20261105-100002-123456-7650"
    assert normalize_fitid("2026091610000276800000000001") == "2026091610000276800000000001"


def test_dates_with_and_without_timezone(fixed_rates):
    txns = _by_fitid(parse_ftfcu_file(FIXTURE))
    # DTPOSTED 20261113000000.000[-08:PST]
    assert txns["20261113-100002-1049-7693"]["transactiondate"] == date(2026, 11, 13)
    # DTPOSTED 20261105 (date only)
    assert txns["20261105-100002-123456-7650"]["transactiondate"] == date(2026, 11, 5)
    assert txns["20261105-100002-123456-7650"]["valuedate"] == date(2026, 11, 5)


def test_native_usd_amounts_are_exact(fixed_rates):
    txns = _by_fitid(parse_ftfcu_file(FIXTURE))
    native = {
        k: json.loads(t["description_structured"])["native_amount"] for k, t in txns.items()
    }
    assert native["20261113-100002-1049-7693"] == -10.49
    assert native["20261105-100002-123456-7650"] == 1234.56
    assert native["20261108-100002-150000-7660"] == -1500.00
    assert all(
        json.loads(t["description_structured"])["native_currency"] == "USD" for t in txns.values()
    )


def test_usd_converted_to_eur_with_ecb_rate(fixed_rates):
    txns = _by_fitid(parse_ftfcu_file(FIXTURE))
    # 2026-11-13 uses the most recent earlier rate (2026-11-02, 1.25).
    t = txns["20261113-100002-1049-7693"]
    assert t["currency"] == "EUR"
    assert t["amount"] == float((Decimal("-10.49") / Decimal("1.25")).quantize(Decimal("0.01")))
    assert json.loads(t["description_structured"])["eur_rate_used"] == 1.25
    # 1234.56 / 1.25 = 987.648 → 987.65
    assert txns["20261105-100002-123456-7650"]["amount"] == 987.65
    # 2026-10-19 uses the rate of 2026-10-16 (1.10): -5.00 / 1.10 = -4.545… → -4.55
    assert txns["20261019-100001-500-2805"]["amount"] == -4.55


def test_without_rates_the_file_is_refused(no_rates):
    from abn_combined.parsers.fx import RatesUnavailableError

    with pytest.raises(RatesUnavailableError, match="Try again later"):
        parse_ftfcu_file(FIXTURE)


def test_description_and_memo(fixed_rates):
    txns = _by_fitid(parse_ftfcu_file(FIXTURE))
    t = txns["20261113-100002-1049-7693"]
    # Whitespace in NAME collapses; the MEMO line at column 0 is read.
    assert t["description"] == "ACH Debit CARD ISSUER PAYM ACH"
    structured = json.loads(t["description_structured"])
    assert structured["memo"] == "ACH Debit"
    assert structured["format"] == "ftfcu"
    assert t["transaction_type_code"] == "DEBIT"


def test_source_lines_are_sequential(fixed_rates):
    txns = parse_ftfcu_file(FIXTURE)
    assert [t["source_line"] for t in txns] == [1, 2, 3, 4, 5]
    assert all(t["source_file"] == FIXTURE.name for t in txns)


def test_qfx_is_refused(tmp_path):
    qfx = tmp_path / "ExportedTransactions.qfx"
    qfx.write_bytes(FIXTURE.read_bytes())
    with pytest.raises(ValueError, match="OFX format"):
        parse_ftfcu_file(qfx)


def test_other_institution_is_refused(tmp_path, no_rates):
    other = tmp_path / "other.ofx"
    other.write_text(
        FIXTURE.read_text()
        .replace("First Tech Federal Credit Union", "Example Bank")
        .replace("<FID>3169", "<FID>1234")
    )
    with pytest.raises(ValueError, match="not from First Tech"):
        parse_ftfcu_file(other)


def test_non_ofx_file_is_refused(tmp_path):
    bad = tmp_path / "bad.ofx"
    bad.write_text("Booking date;Amount\n2026-01-01;1,00\n")
    with pytest.raises(ValueError, match="Cannot read First Tech OFX"):
        parse_ftfcu_file(bad)


# --- shared ECB helpers (moved from the SEB parser) -------------------------


def test_best_rate_lookup_order():
    cache = {date(2026, 11, 2): 1.25, date(2026, 10, 16): 1.10}
    assert fx.best_rate(cache, date(2026, 11, 2)) == 1.25  # exact
    assert fx.best_rate(cache, date(2026, 11, 7)) == 1.25  # earlier business day
    assert fx.best_rate(cache, date(2026, 1, 1)) == 1.10  # before the cache: oldest
    assert fx.best_rate({}, date(2026, 1, 1)) is None


_ECB_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
  xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube>
    <Cube time="2026-11-13"><Cube currency="USD" rate="1.1612"/><Cube currency="SEK" rate="10.95"/></Cube>
    <Cube time="2026-11-12"><Cube currency="USD" rate="1.1590"/><Cube currency="SEK" rate="10.97"/></Cube>
  </Cube>
</gesmes:Envelope>"""


class _Resp:
    def __init__(self, body):
        import io

        self._io = io.BytesIO(body)

    def read(self, *a):
        return self._io.read(*a)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_parse_ecb_xml_selects_currency(monkeypatch):
    monkeypatch.setattr(fx.urllib.request, "urlopen", lambda url, timeout: _Resp(_ECB_XML))
    assert fx.parse_ecb_xml("x", "USD") == {date(2026, 11, 13): 1.1612, date(2026, 11, 12): 1.1590}
    assert fx.parse_ecb_xml("x", "SEK")[date(2026, 11, 13)] == 10.95


def test_seb_wrappers_use_sek(monkeypatch):
    from abn_combined.parsers import seb

    monkeypatch.setattr(fx.urllib.request, "urlopen", lambda url, timeout: _Resp(_ECB_XML))
    assert seb._parse_ecb_xml("x") == {date(2026, 11, 13): 10.95, date(2026, 11, 12): 10.97}
    assert seb._best_rate({date(2026, 11, 12): 10.97}, date(2026, 11, 14)) == 10.97


def test_build_rate_cache_fetches_history_for_old_dates(monkeypatch):
    urls: list[str] = []

    def _fake(url, currency):
        urls.append(url)
        return {date(2026, 9, 1): 1.2} if url == fx._ECB_90D_URL else {date(2025, 1, 2): 1.03}

    monkeypatch.setattr(fx, "parse_ecb_xml", _fake)
    cache = fx.build_rate_cache([date(2025, 6, 1)], "USD")
    assert urls == [fx._ECB_90D_URL, fx._ECB_HIST_URL]
    assert cache == {date(2026, 9, 1): 1.2, date(2025, 1, 2): 1.03}
