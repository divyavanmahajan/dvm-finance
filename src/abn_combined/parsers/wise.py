"""Wise transaction history CSV parser.

Parses the transaction history CSV downloaded from Wise
(wise.com → Statements → All transactions → CSV).

All original CSV fields are stored in description_structured as JSON.

EUR conversion strategy
-----------------------
Every OUT transaction is converted to EUR using the EUR→source_currency rate
from the most recent preceding "Transfer IN" (top-up) that loaded that
currency from EUR.

Lookup order:
  1. Current CSV (rows parsed before this one, sorted by date)
  2. Database (prior uploads) — only if a db session is passed

When source and target are both non-EUR (e.g. SEK wallet paying NOK merchant),
we only look at source_currency — the NOK target is irrelevant because Wise
already did the SEK→NOK conversion internally; what left the wallet was SEK.

If no EUR rate is found (e.g. USD wallet with no EUR top-up history),
the transaction is stored in its native currency as a best effort.
"""

import csv
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def _normalize_name(name: str) -> str:
    """Normalize a person/account name: lowercase, strip spaces and hyphens."""
    return name.lower().replace(" ", "").replace("-", "")


def _wise_account(direction: str, source_name: str, target_name: str) -> str:
    """Derive account identifier.

    OUT: wise-{source_name}  (e.g. wise-divyavanmahajan)
    IN:  wise-{target_name}  (e.g. wise-divyavanmahajan)
    """
    if direction == "OUT":
        return f"wise-{_normalize_name(source_name)}" if source_name else "wise"
    else:
        return f"wise-{_normalize_name(target_name)}" if target_name else "wise"


def _parse_decimal(value: str) -> float | None:
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return float(Decimal(s))
    except (InvalidOperation, ValueError):
        return None


def _parse_date(value: str) -> date | None:
    """Parse datetime string 'YYYY-MM-DD HH:MM:SS' → date."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").date()
    except ValueError:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _lookup_eur_rate_from_db(db, account: str, currency: str, before_date: date) -> float | None:
    """Query the DB for the most recent EUR→currency rate loaded into a Wise wallet.

    Looks for Transfer IN transactions on the wise account where
    source_currency=EUR and target_currency=currency, on or before before_date.
    """
    try:
        from sqlalchemy import text
        sql = text("""
            SELECT json_extract(description_structured, '$.exchange_rate') as rate,
                   transactiondate
            FROM transactions
            WHERE accountNumber = :account
              AND json_extract(description_structured, '$.direction') = 'IN'
              AND json_extract(description_structured, '$.source_currency') = 'EUR'
              AND json_extract(description_structured, '$.target_currency') = :currency
              AND transactiondate <= :before_date
            ORDER BY transactiondate DESC
            LIMIT 1
        """)
        row = db.execute(sql, {"account": account, "currency": currency, "before_date": before_date}).fetchone()
        if row and row[0]:
            rate = _parse_decimal(str(row[0]))
            if rate and rate > 0:
                return rate
    except Exception:
        pass
    return None


def parse_wise_file(file_path: Path, db=None) -> list[dict[str, Any]]:
    """Parse a Wise transaction history CSV and return standardised transactions.

    Args:
        file_path: Path to the Wise CSV export file.
        db: Optional SQLAlchemy session for looking up historical EUR rates
            from prior uploads.

    Returns:
        List of transaction dicts matching the standard transaction schema.
        All OUT transactions are converted to EUR where a rate is available.
        Native amount and currency are always preserved in description_structured.
    """
    file_path = Path(file_path)
    transactions: list[dict[str, Any]] = []

    with open(file_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Pass 1: collect all EUR→currency rates from Transfer IN rows in this CSV.
    # Keyed by currency → list of (date, rate) so we can find the most recent
    # rate on or before any given transaction date (including same-day top-ups).
    csv_eur_rates: dict[str, list[tuple[date, float]]] = {}
    for row in rows:
        if (row.get("Status") or "").strip() in ("CANCELLED", "REFUNDED"):
            continue
        if (row.get("Direction") or "").strip() != "IN":
            continue
        src_ccy = (row.get("Source currency") or "").strip()
        tgt_ccy = (row.get("Target currency") or "").strip()
        if src_ccy != "EUR" or not tgt_ccy or tgt_ccy == "EUR":
            continue
        rate = _parse_decimal((row.get("Exchange rate") or "").strip())
        d = _parse_date((row.get("Created on") or "").strip())
        if rate and rate > 0 and d:
            csv_eur_rates.setdefault(tgt_ccy, []).append((d, rate))

    def _best_csv_rate(currency: str, on_or_before: date) -> float | None:
        """Return the most recent EUR→currency rate from this CSV on or before the given date."""
        entries = [e for e in csv_eur_rates.get(currency, []) if e[0] <= on_or_before]
        if not entries:
            return None
        return max(entries, key=lambda e: e[0])[1]

    for line_num, row in enumerate(rows, start=2):
        status = (row.get("Status") or "").strip()
        if status in ("CANCELLED", "REFUNDED"):
            continue

        wise_id          = (row.get("ID") or "").strip()
        direction        = (row.get("Direction") or "").strip()
        created_on       = (row.get("Created on") or "").strip()
        finished_on      = (row.get("Finished on") or "").strip()
        source_fee_amt   = (row.get("Source fee amount") or "").strip()
        source_fee_ccy   = (row.get("Source fee currency") or "").strip()
        source_name      = (row.get("Source name") or "").strip()
        source_amt_str   = (row.get("Source amount (after fees)") or "").strip()
        source_currency  = (row.get("Source currency") or "").strip()
        target_name      = (row.get("Target name") or "").strip()
        target_amt_str   = (row.get("Target amount (after fees)") or "").strip()
        target_currency  = (row.get("Target currency") or "").strip()
        exchange_rate    = (row.get("Exchange rate") or "").strip()
        reference        = (row.get("Reference") or "").strip()
        wise_category    = (row.get("Category") or "").strip()
        note             = (row.get("Note") or "").strip()

        trans_date = _parse_date(created_on)
        if not trans_date:
            continue

        source_amount = _parse_decimal(source_amt_str) or 0.0
        amount = -source_amount if direction == "OUT" else source_amount

        # Description
        if target_name:
            description = f"{target_name}:{wise_id}"
        elif reference:
            description = f"Wise Transfer:{wise_id}:{reference}"
        else:
            description = f"Wise:{wise_id}"

        # Structured JSON: all original fields always preserved
        structured = {
            "wise_id": wise_id,
            "status": status,
            "direction": direction,
            "created_on": created_on,
            "finished_on": finished_on,
            "source_fee_amount": source_fee_amt or None,
            "source_fee_currency": source_fee_ccy or None,
            "source_name": source_name,
            "source_amount": source_amt_str,
            "source_currency": source_currency,
            "target_name": target_name or None,
            "target_amount": target_amt_str or None,
            "target_currency": target_currency or None,
            "exchange_rate": exchange_rate or None,
            "reference": reference or None,
            "wise_category": wise_category or None,
            "note": note or None,
            "format": "wise",
        }

        account_number = _wise_account(direction, source_name, target_name)
        category = "transfer" if direction == "IN" else None

        # EUR conversion for OUT transactions in non-EUR source currency
        stored_amount = amount
        stored_currency = source_currency or "EUR"

        if direction == "OUT" and source_currency and source_currency != "EUR":
            eur_rate = None

            # 1. Most recent rate from this CSV (two-pass, so same-day top-ups work)
            eur_rate = _best_csv_rate(source_currency, trans_date)

            # 2. Fall back to DB for rates from prior uploads
            if eur_rate is None and db is not None:
                eur_rate = _lookup_eur_rate_from_db(db, account_number, source_currency, trans_date)

            if eur_rate and eur_rate > 0:
                stored_amount = -(source_amount / eur_rate)
                stored_currency = "EUR"
                structured["native_amount"] = source_amt_str
                structured["native_currency"] = source_currency
                structured["eur_rate_used"] = eur_rate

        transactions.append({
            "accountNumber": account_number,
            "transactiondate": trans_date,
            "valuedate": _parse_date(finished_on) or trans_date,
            "amount": round(stored_amount, 2),
            "currency": stored_currency,
            "description": description,
            "description_structured": json.dumps(structured, ensure_ascii=False),
            "category": category,
            "source_file": file_path.name,
            "source_line": line_num,
            "wise_transaction_id": wise_id,
        })

    return transactions
