"""Tests for the SEB kontoutdrag CSV parser.

The parser gets the ECB EUR/SEK rates over the network. The fixture
``fixed_rates`` replaces the rate fetch, so that the tests run offline.
"""

import json
from datetime import date
from pathlib import Path

import pytest

import abn_combined.parsers.seb as seb_mod
from abn_combined.core.dedup import generate_transaction_id, seb_voucher_key
from abn_combined.parsers.fx import RATES_UNAVAILABLE_MESSAGE, RatesUnavailableError
from abn_combined.parsers.seb import is_seb_file, parse_seb_file

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "seb_sample.csv"
SEB_IDS = FIXTURES / "seb_ids.json"


@pytest.fixture(autouse=True)
def fixed_rates(monkeypatch):
    """Give one EUR/SEK rate (11.29) for each date."""
    monkeypatch.setattr(
        seb_mod, "_build_rate_cache", lambda dates: {d: 11.29 for d in dates}
    )


@pytest.fixture
def no_rates(monkeypatch):
    monkeypatch.setattr(seb_mod, "_build_rate_cache", lambda dates: {})


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


def test_seb_amounts_are_in_eur():
    txns = parse_seb_file(FIXTURE)
    assert {t["currency"] for t in txns} == {"EUR"}
    assert txns[0]["amount"] == round(-2779.03 / 11.29, 2)


def test_seb_without_rates_refuses_the_file(no_rates):
    with pytest.raises(RatesUnavailableError, match="not available"):
        parse_seb_file(FIXTURE)


def test_seb_carries_the_krona_values():
    first = parse_seb_file(FIXTURE)[0]
    assert str(first["seb_native_amount"]) == "-2779.030"
    assert str(first["seb_native_balance"]) == "11541.990"
    assert generate_transaction_id(first) == (
        "seb:divyavanmahajan_5484390361_2026-06-25_-2779.03_11541.99"
    )


def test_seb_ids_match_the_shared_fixture():
    data = json.loads(SEB_IDS.read_text())
    for case in data["cases"]:
        trans = {
            "accountNumber": data["account"],
            "transactiondate": date.fromisoformat(case["booking_date"]),
            "seb_voucher_id": case["voucher_number"],
            "seb_native_amount": case["amount"],
            "seb_native_balance": case["balance"],
        }
        assert generate_transaction_id(trans) == case["expected_id"]
        # The migration reads the values as JSON numbers from the structured description.
        as_float = None if case["balance"] is None else float(case["balance"])
        assert seb_voucher_key(
            data["account"], case["voucher_number"], case["booking_date"],
            float(case["amount"]), as_float,
        ) == case["expected_id"]


def test_seb_shared_voucher_gives_different_ids():
    txns = parse_seb_file(FIXTURE)
    shared = [t for t in txns if t["seb_voucher_id"] == "5490990789"]
    assert len(shared) == 4
    assert len({generate_transaction_id(t) for t in shared}) == 4


def test_seb_id_does_not_depend_on_the_rate(monkeypatch):
    first = generate_transaction_id(parse_seb_file(FIXTURE)[0])
    monkeypatch.setattr(seb_mod, "_build_rate_cache", lambda dates: {d: 10.5 for d in dates})
    assert generate_transaction_id(parse_seb_file(FIXTURE)[0]) == first


def test_rates_message_tells_the_user_to_try_again():
    assert "Try again later" in RATES_UNAVAILABLE_MESSAGE


def test_ios_copy_of_the_shared_fixture_is_the_same():
    ios_copy = (
        Path(__file__).parent.parent
        / "ios/DVMFinanceKit/Tests/DVMFinanceKitTests/Fixtures/seb_ids.json"
    )
    assert ios_copy.read_bytes() == SEB_IDS.read_bytes()


def test_is_seb_file_recognizes_the_seb_header():
    assert is_seb_file(FIXTURE)


def test_is_seb_file_rejects_another_csv(tmp_path):
    other = tmp_path / "other.csv"
    other.write_text("date,amount,description\n2026-11-25,-1.00,X\n")
    assert not is_seb_file(other)
    assert not is_seb_file(FIXTURES / "wise_sample.csv")
