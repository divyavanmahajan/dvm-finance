"""SEB bank transaction history CSV parser.

Parses the CSV export from SEB internet banking (kontoutdrag *.csv).

File format:
    Semicolon-delimited, headers on row 1:
    Booking date;Value date;Voucher number;Text;Amount;Balance

EUR conversion strategy
-----------------------
Every transaction is stored in EUR. The native SEK amount is preserved in
description_structured. EUR/SEK reference rates are fetched in a single
request from the ECB XML feed (no API key required):

    90-day:  https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml
    history: https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml

Rate lookup order:
  1. Exact date from ECB feed
  2. Most recent earlier business day in the cache (ECB doesn't publish on weekends/holidays)
  3. If all fetches fail, transactions are stored in SEK as best-effort

Deduplication
-------------
Voucher numbers are unique per transaction at SEB. They are stored in
`seb_voucher_id` on the transaction dict so _generate_transaction_id in
database.py uses account + voucher_number as the primary key, identical to
how wise_transaction_id works.
"""

import csv
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

_ACCOUNT = "seb:divyavanmahajan"
_NATIVE_CURRENCY = "SEK"
_ECB_NS = "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"
_ECB_90D_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
_ECB_HIST_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml"


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
    cache: dict[date, float] = {}
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            tree = ET.parse(resp)
        root = tree.getroot()
        for day_cube in root.findall(f".//{{{_ECB_NS}}}Cube[@time]"):
            day_str = day_cube.get("time")
            if not day_str:
                continue
            try:
                d = datetime.strptime(day_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            for ccy_cube in day_cube.findall(f"{{{_ECB_NS}}}Cube"):
                if ccy_cube.get("currency") == "SEK":
                    try:
                        cache[d] = float(ccy_cube.get("rate", "0"))
                    except (TypeError, ValueError):
                        pass
                    break
    except Exception:
        pass
    return cache


def _build_rate_cache(dates: list[date]) -> dict[date, float]:
    """Return a {date: EUR→SEK rate} cache covering the given dates.

    Fetches the 90-day ECB XML first. If the oldest date in the file predates
    the 90-day window, also fetches the full history XML.
    """
    cache = _parse_ecb_xml(_ECB_90D_URL)

    if dates and cache:
        oldest_needed = min(dates)
        oldest_cached = min(cache)
        if oldest_needed < oldest_cached:
            hist = _parse_ecb_xml(_ECB_HIST_URL)
            cache.update(hist)

    return cache


def _best_rate(cache: dict[date, float], target: date) -> float | None:
    """Return the rate for target, or the most recent earlier rate (weekend/holiday fallback)."""
    if target in cache:
        return cache[target]
    earlier = [d for d in cache if d <= target]
    if earlier:
        return cache[max(earlier)]
    # If target is before all cached dates, use the oldest
    if cache:
        return cache[min(cache)]
    return None


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
