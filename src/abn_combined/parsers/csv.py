"""Generic delimited CSV parsing.

Handles a plain CSV export with the standard ABN-style columns (the same column
mapping used by the XLS parser). PayPal, Wise and SEB have their own dedicated
parsers and are dispatched explicitly, not through this generic path.
"""

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..settings import DEFAULT_CURRENCY
from .description import parse_transaction_description
from .utils import parse_date, parse_decimal

_COLUMN_MAPPING = {
    "accountnumber": "accountNumber",
    "account_number": "accountNumber",
    "mutationcode": "mutationcode",
    "mutation_code": "mutationcode",
    "transactiondate": "transactiondate",
    "transaction_date": "transactiondate",
    "date": "transactiondate",
    "valuedate": "valuedate",
    "value_date": "valuedate",
    "startsaldo": "startsaldo",
    "start_saldo": "startsaldo",
    "startbalance": "startsaldo",
    "endsaldo": "endsaldo",
    "end_saldo": "endsaldo",
    "endbalance": "endsaldo",
    "amount": "amount",
    "description": "description",
}


def parse_csv_file(file_path: Path) -> list[dict[str, Any]]:
    """Parse a generic CSV file into standardized transactions."""
    file_path = Path(file_path)
    try:
        df = pd.read_csv(file_path, sep=None, engine="python")
    except Exception as exc:  # noqa: BLE001 - normalise to a clear error
        raise ValueError(f"Error parsing CSV file: {exc}") from exc

    df.columns = df.columns.str.lower().str.strip()
    df = df.rename(columns=_COLUMN_MAPPING)

    if "amount" not in df.columns or "transactiondate" not in df.columns:
        raise ValueError(
            "CSV missing required columns 'amount' and/or 'date'. "
            "Use the PayPal/Wise/SEB format if this is one of those exports."
        )

    transactions: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        description = str(row.get("description", ""))
        trans = {
            "accountNumber": str(row.get("accountNumber", "")),
            "mutationcode": str(row.get("mutationcode", "")),
            "transactiondate": parse_date(row.get("transactiondate")),
            "valuedate": parse_date(row.get("valuedate")),
            "startsaldo": parse_decimal(row.get("startsaldo")),
            "endsaldo": parse_decimal(row.get("endsaldo")),
            "amount": parse_decimal(row.get("amount", 0)),
            "description": description,
            "currency": (
                str(row.get("currency", DEFAULT_CURRENCY)).upper()
                if pd.notna(row.get("currency"))
                else DEFAULT_CURRENCY
            ),
            "source_line": int(idx) + 2,
            "source_file": file_path.name,
        }
        structured = parse_transaction_description(description)
        if structured:
            trans["description_structured"] = json.dumps(structured, ensure_ascii=False)
        transactions.append(trans)

    return transactions
