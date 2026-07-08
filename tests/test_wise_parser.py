"""Tests for the Wise transaction-history CSV parser."""

from datetime import date
from pathlib import Path

from abn_combined.parsers.wise import parse_wise_file

FIXTURE = Path(__file__).parent / "fixtures" / "wise_sample.csv"


def test_parse_wise_basic():
    txns = parse_wise_file(FIXTURE)
    # CANCELLED row is dropped; 3 remain.
    assert len(txns) == 3
    ids = {t["wise_transaction_id"] for t in txns}
    assert ids == {"TRANSFER-1", "TRANSFER-2", "TRANSFER-3"}


def test_wise_in_transfer_categorized_transfer():
    txns = {t["wise_transaction_id"]: t for t in parse_wise_file(FIXTURE)}
    inbound = txns["TRANSFER-1"]
    assert inbound["category"] == "transfer"
    assert inbound["amount"] > 0
    assert inbound["transactiondate"] == date(2024, 1, 5)


def test_wise_out_eur_native():
    txns = {t["wise_transaction_id"]: t for t in parse_wise_file(FIXTURE)}
    out_eur = txns["TRANSFER-3"]
    assert out_eur["amount"] == -50.0
    assert out_eur["currency"] == "EUR"


def test_wise_out_sek_converted_to_eur_via_topup_rate():
    # TRANSFER-1 loaded SEK at EUR->SEK rate 11.5; TRANSFER-2 spends 230 SEK.
    txns = {t["wise_transaction_id"]: t for t in parse_wise_file(FIXTURE)}
    out_sek = txns["TRANSFER-2"]
    assert out_sek["currency"] == "EUR"
    # 230 / 11.5 = 20.00
    assert out_sek["amount"] == -20.0
