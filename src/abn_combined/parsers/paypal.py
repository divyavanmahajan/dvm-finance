"""PayPal Activity Report parser.

Parses the "Activity report for balance affecting transactions" (TAB-delimited)
from https://www.paypal.com/reports/dlog

See web2/specs/PAYPAL_UPLOAD_SPEC.md for full specification.
"""

import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any


def _parse_european_number(value: str) -> Decimal | None:
    """Parse European number format: comma=decimal, period=thousands.

    Examples: -89,71 -> -89.71, 1.458,32 -> 1458.32
    """
    if not value or not isinstance(value, str):
        return None
    s = value.strip().strip('"')
    if not s:
        return None
    try:
        # Remove thousands separator (period), replace decimal (comma) with period
        s = s.replace(".", "").replace(",", ".")
        return Decimal(s)
    except Exception:
        return None


def _parse_date(value: str) -> date | None:
    """Parse date from DD/MM/YYYY."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip().strip('"')
    if not s:
        return None
    try:
        parts = s.split("/")
        if len(parts) != 3:
            return None
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


def _email_to_account(email: str) -> str:
    """Derive account identifier from email: pp:{local_part}."""
    if not email or not isinstance(email, str):
        return "pp:unknown"
    e = email.strip().strip('"')
    if not e or "@" not in e:
        return "pp:unknown"
    local = e.split("@")[0].strip()
    return f"pp:{local}" if local else "pp:unknown"


def _get_account_from_row(row: dict[str, str]) -> str:
    """Derive account from row: From Email when Debit, To Email when Credit."""
    balance_impact = (row.get("Balance Impact") or "").strip().strip('"')
    if balance_impact == "Debit":
        email = row.get("From Email Address") or ""
    else:
        email = row.get("To Email Address") or ""
    return _email_to_account(email)


def _row_to_snake_case(row: dict[str, str]) -> dict[str, Any]:
    """Convert row keys to snake_case and values to suitable types."""
    result = {}
    for k, v in row.items():
        key = k.replace(" ", "_").replace("/", "_").replace("-", "_").lower()
        key = "".join(c for c in key if c.isalnum() or c == "_")
        if v is not None and str(v).strip():
            result[key] = v.strip().strip('"') if isinstance(v, str) else v
        else:
            result[key] = v
    return result


def parse_paypal_file(file_path: Path) -> list[dict[str, Any]]:
    """Parse PayPal activity report (TAB-delimited) and return standardized transactions.

    Args:
        file_path: Path to the PayPal report file

    Returns:
        List of transaction dicts matching the standard transaction schema
    """
    file_path = Path(file_path)
    transactions: list[dict[str, Any]] = []
    rows: list[dict[str, str]] = []

    with open(file_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
        for row in reader:
            # Strip quotes from values
            cleaned = {
                k.strip().strip('"'): (v.strip().strip('"') if v else "")
                for k, v in row.items()
                if k
            }
            rows.append(cleaned)

    if not rows:
        return []

    # Build index: ref_txn_id -> list of child rows (same timestamp group)
    # Group rows by (Date, Time) for linking
    ref_to_rows: dict[str, list[dict]] = {}
    parent_txn_ids: set = set()

    for i, row in enumerate(rows):
        ref_id = (row.get("Reference Txn ID") or "").strip()
        txn_id = (row.get("Transaction ID") or "").strip()
        if ref_id:
            ref_to_rows.setdefault(ref_id, []).append((i, row))
        else:
            parent_txn_ids.add(txn_id)

    # Find EUR funding row for non-EUR parents: ref_id -> (row_index, eur_net)
    eur_funding_for_parent: dict[str, tuple] = {}
    for ref_id, children in ref_to_rows.items():
        for idx, child in children:
            name = (child.get("Name") or "").strip()
            ttype = (child.get("Type") or "").strip()
            curr = (child.get("Currency") or "").strip().upper()
            if not name and curr == "EUR":
                if "Bank Deposit to PP Account" in ttype or "User Initiated Withdrawal" in ttype:
                    net = _parse_european_number(child.get("Net") or "0")
                    if net is not None:
                        eur_funding_for_parent[ref_id] = (idx, child, float(net))
                        break

    # Process rows
    bank_deposit_type = "Bank Deposit to PP Account "
    user_withdrawal_type = "User Initiated Withdrawal"

    for line_num, row in enumerate(rows, start=2):  # Line 1 is header
        name = (row.get("Name") or "").strip()
        ttype = (row.get("Type") or "").strip()
        txn_id = (row.get("Transaction ID") or "").strip()
        ref_id = (row.get("Reference Txn ID") or "").strip()
        currency = (row.get("Currency") or "").strip().upper()
        net_val = _parse_european_number(row.get("Net") or "0")
        net = float(net_val) if net_val is not None else 0.0

        account = _get_account_from_row(row)
        trans_date = _parse_date(row.get("Date") or "")
        if not trans_date:
            continue

        # Build raw row for description_structured (snake_case keys)
        raw = _row_to_snake_case(row)
        raw["paypal_transaction_id"] = txn_id
        raw["paypal_type"] = ttype
        raw["paypal_balance_impact"] = (row.get("Balance Impact") or "").strip()

        # Rule 1: Rows with Name
        if name:
            item_title = (row.get("Item Title") or "").strip()
            # Description: Name + ":" + Transaction ID + ":" + Item Title (if empty, use Name only)
            if item_title:
                description = f"{name}:{txn_id}:{item_title}"
            else:
                description = f"{name}:{txn_id}"

            amount = net
            curr_stored = currency

            # Non-EUR: get EUR amount from linked Bank Deposit/User Initiated Withdrawal
            # Look up by this row's txn_id (parent); children have ref_id = parent txn_id
            if currency != "EUR":
                funding = eur_funding_for_parent.get(txn_id)
                if funding:
                    _, _, eur_net = funding
                    amount = -abs(eur_net) if net < 0 else abs(eur_net)
                    curr_stored = "EUR"
                    raw["original_currency"] = currency
                    raw["original_amount"] = float(net)
                    raw["eur_amount"] = amount
                    raw["eur_currency"] = "EUR"

            trans = {
                "accountNumber": account,
                "transactiondate": trans_date,
                "amount": amount,
                "currency": curr_stored,
                "description": description,
                "description_structured": json.dumps(raw, ensure_ascii=False),
                "category": None,
                "source_file": file_path.name,
                "source_line": line_num,
                "paypal_transaction_id": txn_id,
            }
            transactions.append(trans)
            continue

        # Rule 2: Bank Deposit or User Initiated Withdrawal (no Name)
        if ttype.rstrip() == bank_deposit_type.rstrip() or ttype == user_withdrawal_type:
            # Exception: when this row is EUR funding for a non-EUR parent payment, skip
            is_eur_funding_for_foreign = False
            if ref_id and currency == "EUR":
                for p in rows:
                    if (p.get("Transaction ID") or "").strip() == ref_id:
                        p_curr = (p.get("Currency") or "").strip().upper()
                        if p_curr != "EUR":
                            is_eur_funding_for_foreign = True
                        break

            if is_eur_funding_for_foreign:
                continue  # Skip - used for parent transaction only

            # Description: Type + ":" + Reference Txn ID
            description = f"{ttype}:{ref_id}" if ref_id else ttype

            trans = {
                "accountNumber": account,
                "transactiondate": trans_date,
                "amount": net,
                "currency": "EUR",
                "description": description,
                "description_structured": json.dumps(raw, ensure_ascii=False),
                "category": "transfer-paypal",
                "source_file": file_path.name,
                "source_line": line_num,
                "paypal_transaction_id": txn_id,
            }
            transactions.append(trans)

        # Rule 3: Other rows without Name (General Currency Conversion, etc.) - skip

    return transactions
