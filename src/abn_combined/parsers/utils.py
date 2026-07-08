"""Shared parsing utilities."""

import json
from pathlib import Path
from typing import Any

import pandas as pd


def save_to_csv(transactions: list[dict[str, Any]], output_path: Path):
    """Save transactions to CSV file."""
    df = pd.DataFrame(transactions)
    df.to_csv(output_path, index=False)


def save_to_json(transactions: list[dict[str, Any]], output_path: Path):
    """Save transactions to JSON file."""
    # Convert dates and decimals to strings for JSON serialization
    json_transactions = []
    for trans in transactions:
        json_trans = {}
        for key, value in trans.items():
            if hasattr(value, "isoformat"):  # Date objects
                json_trans[key] = value.isoformat()
            elif isinstance(value, (int, float)) or value is None:
                json_trans[key] = value
            else:
                json_trans[key] = str(value)
        json_transactions.append(json_trans)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_transactions, f, indent=2, ensure_ascii=False)


def parse_date(date_value) -> Any:
    """Parse date from various formats."""
    from datetime import date

    if pd.isna(date_value) or date_value is None or date_value == "":
        return None

    if isinstance(date_value, (pd.Timestamp, date)):
        return date_value.date() if hasattr(date_value, "date") else date_value

    try:
        return pd.to_datetime(date_value).date()
    except Exception:
        return None


def parse_decimal(value) -> Any:
    """Parse decimal from various formats."""
    if pd.isna(value) or value is None or value == "":
        return None

    try:
        if isinstance(value, str):
            # Remove currency symbols and spaces
            value = value.replace("€", "").replace(",", ".").strip()
        return float(value)
    except Exception:
        return None

