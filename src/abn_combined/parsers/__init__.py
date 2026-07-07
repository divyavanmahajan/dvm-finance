"""Statement parsers and the file-dispatch interface."""

from pathlib import Path
from typing import Any

from .csv import parse_csv_file
from .description import parse_transaction_description
from .mt940 import parse_mt940_file
from .paypal import parse_paypal_file
from .seb import parse_seb_file
from .utils import save_to_csv, save_to_json
from .wise import parse_wise_file
from .xls import parse_xls_file


def parse_statement_file(file_path: Path) -> list[dict[str, Any]]:
    """Parse an MT940/MTA/STA/TXT or XLS/XLSX statement file.

    PayPal, Wise and SEB exports (all ``.txt``/``.csv``) are dispatched explicitly
    by the importer, not auto-detected here.
    """
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()
    source_file_name = file_path.name

    if suffix in [".mt940", ".mta", ".sta", ".txt"]:
        transactions = parse_mt940_file(file_path)
    elif suffix in [".xls", ".xlsx"]:
        transactions = parse_xls_file(file_path)
    elif suffix == ".csv":
        transactions = parse_csv_file(file_path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    for trans in transactions:
        trans["source_file"] = source_file_name

    return transactions


__all__ = [
    "parse_statement_file",
    "parse_mt940_file",
    "parse_xls_file",
    "parse_csv_file",
    "parse_paypal_file",
    "parse_wise_file",
    "parse_seb_file",
    "parse_transaction_description",
    "save_to_csv",
    "save_to_json",
]
