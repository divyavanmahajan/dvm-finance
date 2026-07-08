"""XLS/XLSX file parsing."""

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..settings import DEFAULT_CURRENCY
from .description import parse_transaction_description
from .utils import parse_date, parse_decimal


def parse_xls_file(file_path: Path) -> list[dict[str, Any]]:
    """Parse XLS/XLSX file and return list of transactions."""
    try:
        # Read Excel file - use appropriate engine based on file extension
        file_ext = file_path.suffix.lower()
        if file_ext == ".xls":
            # Use xlrd engine for old .xls format
            df = pd.read_excel(file_path, engine="xlrd")
        else:
            # Use openpyxl engine for .xlsx format
            df = pd.read_excel(file_path, engine="openpyxl")

        # Normalize column names (handle case variations)
        column_mapping = {
            "accountnumber": "accountNumber",
            "account_number": "accountNumber",
            "mutationcode": "mutationcode",
            "mutation_code": "mutationcode",
            "transactiondate": "transactiondate",
            "transaction_date": "transactiondate",
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

        # Rename columns
        df.columns = df.columns.str.lower().str.strip()
        df = df.rename(columns=column_mapping)

        # Convert to list of dictionaries
        transactions = []
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
                "source_line": int(idx)
                + 2,  # Excel row number (1-based header + 1-based index)
            }
            # Parse structured description
            structured = parse_transaction_description(description)
            if structured:
                trans["description_structured"] = json.dumps(
                    structured, ensure_ascii=False
                )
            transactions.append(trans)

        return transactions
    except Exception as e:
        raise ValueError(f"Error parsing XLS file: {e}") from e

