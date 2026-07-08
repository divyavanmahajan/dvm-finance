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


class TestPayPalParser(unittest.TestCase):
    def test_parse_european_number(self):
        self.assertAlmostEqual(float(_parse_european_number("-89,71")), -89.71)
        self.assertAlmostEqual(float(_parse_european_number("1.458,32")), 1458.32)
        self.assertAlmostEqual(float(_parse_european_number("89,71")), 89.71)
        self.assertIsNone(_parse_european_number(""))
        self.assertIsNone(_parse_european_number(None))

    def test_parse_date(self):
        self.assertEqual(_parse_date("13/08/2025"), date(2025, 8, 13))
        self.assertEqual(_parse_date("01/01/2024"), date(2024, 1, 1))
        self.assertIsNone(_parse_date(""))
        self.assertIsNone(_parse_date("invalid"))

    def test_email_to_account(self):
        self.assertEqual(_email_to_account("paypaleu@dvanm.cotse.net"), "pp:paypaleu")
        self.assertEqual(_email_to_account("user@example.com"), "pp:user")
        self.assertEqual(_email_to_account(""), "pp:unknown")
        self.assertEqual(_email_to_account("no-at-sign"), "pp:unknown")

    def test_parse_paypal_file(self):
        transactions = parse_paypal_file(FIXTURE)
        self.assertGreater(len(transactions), 0)

        first = transactions[0]
        self.assertEqual(first["accountNumber"], "pp:paypaleu")
        self.assertEqual(first["transactiondate"], date(2025, 8, 13))
        self.assertAlmostEqual(first["amount"], -89.71)
        self.assertEqual(first["currency"], "EUR")
        self.assertTrue(first["description"].startswith("kinoheld"))
        self.assertIn("18X96129H8498560R", first["description"])
        parts = first["description"].split(":")
        self.assertGreaterEqual(len(parts), 2)

        second = transactions[1]
        self.assertEqual(second["category"], "transfer-paypal")
        self.assertAlmostEqual(second["amount"], 89.71)
        self.assertIn("Bank Deposit", second["description"])
        self.assertIn("18X96129H8498560R", second["description"])

        ukba = [t for t in transactions if "UKBA" in (t.get("description") or "")]
        if ukba:
            self.assertAlmostEqual(ukba[0]["amount"], -1458.32)
            self.assertEqual(ukba[0]["currency"], "EUR")

    def test_paypal_id_present(self):
        transactions = parse_paypal_file(FIXTURE)
        assert all(t.get("paypal_transaction_id") for t in transactions)


if __name__ == "__main__":
    unittest.main()
