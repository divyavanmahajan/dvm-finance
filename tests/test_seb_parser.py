"""Tests for the SEB kontoutdrag CSV parser.

Note: the parser fetches ECB EUR/SEK rates over the network to convert to EUR.
These tests assert on the network-independent parts (native amount, voucher id,
row structure) so they pass offline.
"""

from datetime import date
from pathlib import Path

from abn_combined.parsers.seb import parse_seb_file

FIXTURE = Path(__file__).parent / "fixtures" / "seb_sample.csv"


def test_parse_seb_rows():
    txns = parse_seb_file(FIXTURE)
    assert len(txns) > 0
    first = txns[0]
    assert first["accountNumber"] == "seb:divyavanmahajan"
    assert first["seb_voucher_id"] == "5484390361"
    assert first["transactiondate"] == date(2026, 6, 25)


def test_seb_native_amount_preserved():
    import json

    txns = parse_seb_file(FIXTURE)
    structured = json.loads(txns[0]["description_structured"])
    assert structured["format"] == "seb"
    assert structured["native_currency"] == "SEK"
    # Native SEK amount from the fixture's first row.
    assert structured["native_amount"] == -2779.03


def test_seb_all_rows_have_voucher():
    txns = parse_seb_file(FIXTURE)
    assert all(t["seb_voucher_id"] for t in txns)
