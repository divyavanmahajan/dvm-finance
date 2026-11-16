"""SEB bank transaction history CSV parser.

Parses the CSV export from SEB internet banking (kontoutdrag *.csv).

File format:
    Semicolon-delimited, headers on row 1:
    Booking date;Value date;Voucher number;Text;Amount;Balance

EUR conversion strategy
-----------------------
Every transaction is stored in EUR. The native SEK amount is preserved in
description_structured. The EUR/SEK reference rates come from the ECB feed;
see ``parsers/fx.py`` for the feed and the rate lookup order. If all fetches
fail, transactions are stored in SEK as best-effort.

Deduplication
-------------
Voucher numbers are unique per transaction at SEB. They are stored in
`seb_voucher_id` on the transaction dict so _generate_transaction_id in
database.py uses account + voucher_number as the primary key, identical to
how wise_transaction_id works.
"""

import csv
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .fx import best_rate, build_rate_cache, parse_ecb_xml

_ACCOUNT = "seb:divyavanmahajan"
_NATIVE_CURRENCY = "SEK"


def _parse_decimal(value: str) -> float | None:
    if not value or not isinstance(value, str):
        return None
    s = value.strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(Decimal(s))
    except (InvalidOperation, ValueError):
        return None


def _parse_date(value: str) -> date | None:
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_ecb_xml(url: str) -> dict[date, float]:
    """Fetch and parse an ECB eurofxref XML file, returning {date: EUR/SEK rate}."""
    return parse_ecb_xml(url, _NATIVE_CURRENCY)


def _build_rate_cache(dates: list[date]) -> dict[date, float]:
    """Return a {date: EUR→SEK rate} cache covering the given dates."""
    return build_rate_cache(dates, _NATIVE_CURRENCY)


def _best_rate(cache: dict[date, float], target: date) -> float | None:
    """Return the rate for target, or the most recent earlier rate (weekend/holiday fallback)."""
    return best_rate(cache, target)


def parse_seb_file(file_path: Path) -> list[dict[str, Any]]:
    """Parse a SEB kontoutdrag CSV and return standardised transactions.

    Args:
        file_path: Path to the SEB CSV export.

    Returns:
        List of transaction dicts matching the standard transaction schema.
        All transactions are converted from SEK to EUR where a rate is
        available. Native amounts and the rate used are stored in
        description_structured.
    """
    file_path = Path(file_path)
    transactions: list[dict[str, Any]] = []

    # Try UTF-8-sig first (handles BOM), fall back to latin-1 for Swedish chars
    content = None
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            with open(file_path, encoding=encoding) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        raise ValueError(f"Cannot decode SEB CSV file: {file_path}")

    reader = csv.DictReader(content.splitlines(), delimiter=";")
    rows = list(reader)

    if not rows:
        return transactions

    # Validate expected headers
    expected = {"Booking date", "Value date", "Voucher number", "Text", "Amount", "Balance"}
    actual = set(reader.fieldnames or [])
    missing = expected - actual
    if missing:
        raise ValueError(
            f"SEB CSV missing expected columns: {missing}. "
            f"Found: {actual}. Is this a SEB kontoutdrag export?"
        )

    # Collect unique booking dates for rate pre-fetching
    booking_dates: list[date] = []
    for row in rows:
        d = _parse_date(row.get("Booking date", ""))
        if d:
            booking_dates.append(d)

    rate_cache = _build_rate_cache(booking_dates)

    for line_num, row in enumerate(rows, start=2):
        booking_date = _parse_date(row.get("Booking date", ""))
        value_date = _parse_date(row.get("Value date", ""))
        voucher = (row.get("Voucher number") or "").strip()
        text = (row.get("Text") or "").strip()
        amount_sek = _parse_decimal(row.get("Amount", ""))
        balance_sek = _parse_decimal(row.get("Balance", ""))

        if booking_date is None or amount_sek is None:
            continue

        structured: dict[str, Any] = {
            "format": "seb",
            "voucher_number": voucher or None,
            "native_amount": amount_sek,
            "native_currency": _NATIVE_CURRENCY,
            "native_balance": balance_sek,
        }

        # EUR conversion
        eur_rate = _best_rate(rate_cache, booking_date)
        if eur_rate and eur_rate > 0:
            stored_amount = round(amount_sek / eur_rate, 2)
            stored_balance = round(balance_sek / eur_rate, 2) if balance_sek is not None else None
            stored_currency = "EUR"
            structured["eur_rate_used"] = eur_rate
        else:
            stored_amount = amount_sek
            stored_balance = balance_sek
            stored_currency = _NATIVE_CURRENCY

        transactions.append({
            "accountNumber": _ACCOUNT,
            "transactiondate": booking_date,
            "valuedate": value_date or booking_date,
            "amount": stored_amount,
            "currency": stored_currency,
            "description": text,
            "description_structured": json.dumps(structured, ensure_ascii=False),
            "endsaldo": stored_balance,
            "source_file": file_path.name,
            "source_line": line_num,
            "seb_voucher_id": voucher if voucher else None,
        })

    return transactions
