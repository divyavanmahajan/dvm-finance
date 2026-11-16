"""Tests for PayPal activity report parser (ported from abn-analyst)."""

import unittest
from datetime import date
from pathlib import Path

from abn_combined.parsers.paypal import (
    _email_to_account,
    _parse_date,
    _parse_european_number,
    parse_paypal_file,
)

FIXTURE = Path(__file__).parent / "fixtures" / "paypal_sample.TXT"
# Made-up report in the English number format (period as the decimal separator).
PERIOD_FIXTURE = Path(__file__).parent / "fixtures" / "paypal_period_decimal.TXT"


class TestPayPalParser(unittest.TestCase):
    def test_parse_european_number(self):
        self.assertAlmostEqual(float(_parse_european_number("-89,71")), -89.71)
        self.assertAlmostEqual(float(_parse_european_number("1.458,32")), 1458.32)
        self.assertAlmostEqual(float(_parse_european_number("89,71")), 89.71)
        self.assertIsNone(_parse_european_number(""))
        self.assertIsNone(_parse_european_number(None))

    def test_parse_number_finds_the_decimal_separator(self):
        cases = {
            "-12,34": -12.34,
            "-12.34": -12.34,
            "1.458,32": 1458.32,
            "1,458.32": 1458.32,
            "1.458": 1458,
            "1,458": 1458,
            "1,5": 1.5,
            "1.5": 1.5,
            "1.234.567,89": 1234567.89,
            "1,234,567.89": 1234567.89,
            "0,00": 0,
            "12": 12,
            '"-12.34"': -12.34,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertAlmostEqual(float(_parse_european_number(raw)), expected)

    def test_parse_number_rejects_text(self):
        self.assertIsNone(_parse_european_number("abc"))
        self.assertIsNone(_parse_european_number("   "))

    def test_parse_date(self):
        self.assertEqual(_parse_date("13/08/2025"), date(2025, 8, 13))
        self.assertEqual(_parse_date("01/01/2024"), date(2024, 1, 1))
        self.assertIsNone(_parse_date(""))
        self.assertIsNone(_parse_date("invalid"))

    def test_email_to_account(self):
        self.assertEqual(_email_to_account("buyer@example.com"), "pp:buyer")
        self.assertEqual(_email_to_account("user@example.com"), "pp:user")
        self.assertEqual(_email_to_account(""), "pp:unknown")
        self.assertEqual(_email_to_account("no-at-sign"), "pp:unknown")

    def test_parse_report_with_period_decimals(self):
        transactions = parse_paypal_file(PERIOD_FIXTURE)
        amounts = {t["paypal_transaction_id"]: t["amount"] for t in transactions}
        self.assertAlmostEqual(amounts["TESTDOT0000000001"], -12.34)
        self.assertAlmostEqual(amounts["TESTDOT0000000003"], -1458.32)
        for t in transactions:
            self.assertLess(abs(t["amount"]), 10_000)

    def test_parse_paypal_file(self):
        transactions = parse_paypal_file(FIXTURE)
        self.assertGreater(len(transactions), 0)

        first = transactions[0]
        self.assertEqual(first["accountNumber"], "pp:buyer")
        self.assertEqual(first["transactiondate"], date(2025, 8, 13))
        self.assertAlmostEqual(first["amount"], -89.71)
        self.assertEqual(first["currency"], "EUR")
        self.assertTrue(first["description"].startswith("fcgiavzz"))
        self.assertIn("05V70015O4828420M", first["description"])
        parts = first["description"].split(":")
        self.assertGreaterEqual(len(parts), 2)

        second = transactions[1]
        self.assertEqual(second["category"], "transfer-paypal")
        self.assertAlmostEqual(second["amount"], 89.71)
        self.assertIn("Bank Deposit", second["description"])
        self.assertIn("05V70015O4828420M", second["description"])

        ukba = [t for t in transactions if "UKBA" in (t.get("description") or "")]
        if ukba:
            self.assertAlmostEqual(ukba[0]["amount"], -1458.32)
            self.assertEqual(ukba[0]["currency"], "EUR")

    def test_paypal_id_present(self):
        transactions = parse_paypal_file(FIXTURE)
        assert all(t.get("paypal_transaction_id") for t in transactions)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# A non-EUR payment with no EUR funding row: ECB reference rate, as for SEB
# ---------------------------------------------------------------------------

UNFUNDED = Path(__file__).parent / "fixtures" / "paypal_usd_unfunded.TXT"


def _ecb(monkeypatch, cache):
    import abn_combined.parsers.paypal as paypal_mod

    calls: list[tuple] = []

    def _fake(dates, currency):
        calls.append((sorted(set(dates)), currency))
        return dict(cache)

    monkeypatch.setattr(paypal_mod, "build_rate_cache", _fake)
    return calls


def test_unfunded_usd_payment_uses_ecb_rate(monkeypatch):
    import json

    calls = _ecb(monkeypatch, {date(2025, 12, 23): 1.15, date(2026, 1, 2): 1.20})
    by_id = {t["paypal_transaction_id"]: t for t in parse_paypal_file(UNFUNDED)}

    # The USD payments and the USD deposit ask for rates, in one request for USD.
    assert calls == [([date(2025, 12, 28), date(2026, 1, 3)], "USD")]

    small = by_id["TESTUSD0000000001"]  # 2025-12-28 → most recent earlier rate 1.15
    assert small["currency"] == "EUR"
    assert small["amount"] == -6.0  # -6.90 / 1.15
    raw = json.loads(small["description_structured"])
    assert raw["original_amount"] == -6.90
    assert raw["original_currency"] == "USD"
    assert raw["eur_rate_used"] == 1.15
    assert raw["eur_conversion"] == "ecb_reference_rate"

    large = by_id["TESTUSD0000000002"]  # -1.234,56 / 1.20 = -1028.80
    assert large["amount"] == -1028.8
    assert json.loads(large["description_structured"])["original_amount"] == -1234.56

    # The USD bank deposit that funds the subscription converts at the same
    # rate, so the pair nets to zero in EUR.
    deposit = by_id["TESTDEP0000000004"]
    assert deposit["currency"] == "EUR"
    assert deposit["amount"] == 6.0
    assert deposit["category"] == "transfer-paypal"
    raw_dep = json.loads(deposit["description_structured"])
    assert raw_dep["original_amount"] == 6.90
    assert raw_dep["original_currency"] == "USD"

    euro = by_id["TESTEUR0000000003"]
    assert euro["amount"] == -12.5
    assert "original_currency" not in json.loads(euro["description_structured"])


def test_unfunded_usd_payment_without_rates_stays_in_usd(monkeypatch):
    import json

    _ecb(monkeypatch, {})
    by_id = {t["paypal_transaction_id"]: t for t in parse_paypal_file(UNFUNDED)}
    t = by_id["TESTUSD0000000001"]
    assert t["currency"] == "USD"
    assert t["amount"] == -6.90
    assert "original_currency" not in json.loads(t["description_structured"])
    # The deposit keeps its own currency too; it is not labelled EUR.
    assert by_id["TESTDEP0000000004"]["currency"] == "USD"
    assert by_id["TESTDEP0000000004"]["amount"] == 6.90


def test_funded_payment_keeps_paypal_eur_amount(monkeypatch):
    """A payment with an EUR funding row keeps the EUR that PayPal took; no ECB fetch."""
    import json

    calls = _ecb(monkeypatch, {date(2020, 1, 1): 99.0})
    converted = [
        t for t in parse_paypal_file(FIXTURE)
        if "original_currency" in json.loads(t["description_structured"])
    ]
    assert converted
    assert calls == []
    for t in converted:
        raw = json.loads(t["description_structured"])
        assert raw["eur_conversion"] == "paypal_funding"
        assert "eur_rate_used" not in raw
