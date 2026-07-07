"""MT940/STA/MTA file parsing."""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from ..settings import DEFAULT_CURRENCY
from .description import parse_transaction_description
from .utils import parse_date, parse_decimal

# Try to import the parser library
try:
    try:
        from abnamroparser.tsvparser import convert_tsv_to_json_like, read_tsv

        PARSER_AVAILABLE = True
    except ImportError:
        try:
            # Alternative: try old import path
            from abn_amro_statement_parser import parse_statement

            PARSER_AVAILABLE = True

            # Create wrapper function
            def read_tsv(file_path):
                return parse_statement(file_path)

            def convert_tsv_to_json_like(data):
                return data

        except ImportError:
            PARSER_AVAILABLE = False
            read_tsv = None
            convert_tsv_to_json_like = None
except ImportError:
    PARSER_AVAILABLE = False
    read_tsv = None
    convert_tsv_to_json_like = None


def _parse_mt940_basic(file_path: Path) -> list[dict[str, Any]]:
    """Basic MT940 parser for STA/MT940 files."""
    transactions = []
    current_transaction = {}
    account_number = ""
    start_balance = None
    end_balance = None

    with open(file_path, encoding="utf-8") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Account number (:25:)
        if line.startswith(":25:"):
            account_number = line[4:].strip()

        # Starting balance (:60F:)
        elif line.startswith(":60F:"):
            # Format: :60F:C240515EUR151,31
            balance_str = line[5:].strip()
            if balance_str:
                try:
                    # Extract date and amount
                    # C240515 = Credit, 24/05/15
                    # EUR151,31
                    date_part = balance_str[1:7]  # YYMMDD
                    year = 2000 + int(date_part[0:2])
                    month = int(date_part[2:4])
                    day = int(date_part[4:6])

                    start_balance = float(balance_str.split("EUR")[1].replace(",", "."))
                except Exception:
                    pass

        # Transaction (:61:)
        elif line.startswith(":61:"):
            # Save previous transaction if it exists and has a description
            if (
                current_transaction
                and "description" in current_transaction
                and current_transaction.get("description")
            ):
                current_transaction["startsaldo"] = start_balance
                current_transaction["endsaldo"] = end_balance
                current_transaction["valuedate"] = current_transaction.get(
                    "transactiondate"
                )
                current_transaction["mutationcode"] = ""
                if "currency" not in current_transaction:
                    current_transaction["currency"] = DEFAULT_CURRENCY
                transactions.append(current_transaction)

            # Format: :61:2405160516D5,75N426NONREF
            trans_line = line[4:].strip()
            if trans_line:
                try:
                    # Extract date (YYMMDD), value date (MMDD), amount, transaction type code, and reference
                    date_str = trans_line[0:6]  # YYMMDD
                    year = 2000 + int(date_str[0:2])
                    month = int(date_str[2:4])
                    day = int(date_str[4:6])

                    transaction_date = date(year, month, day)

                    # Extract amount (D for debit, C for credit), transaction type code, and reference
                    amount = None
                    transaction_type_code = None
                    reference = None

                    for j in range(6, len(trans_line)):
                        if trans_line[j] in ["D", "C"]:
                            # Find the amount after D/C
                            # Amount ends at "N" (start of transaction type code) or end of string
                            remaining = trans_line[j + 1 :]

                            # Find where amount ends (at "N" for transaction type code)
                            n_index = remaining.find("N")
                            if n_index > 0:
                                amount_part = remaining[:n_index]
                                amount = float(amount_part.replace(",", "."))
                                if trans_line[j] == "D":
                                    amount = -amount  # Debit is negative

                                # Extract transaction type code (starts with "N" followed by digits)
                                # Format: N426 or similar - this applies to both D and C transactions
                                type_code_start = j + 1 + n_index
                                type_code_remaining = trans_line[
                                    type_code_start + 1 :
                                ]  # Skip the "N"

                                # Transaction type code is digits after "N", reference is after that
                                # Find where digits end (start of reference)
                                type_code_match = re.match(
                                    r"^(\d+)", type_code_remaining
                                )
                                if type_code_match:
                                    transaction_type_code = "N" + type_code_match.group(
                                        1
                                    )
                                    reference_start = (
                                        type_code_start
                                        + 1
                                        + len(type_code_match.group(1))
                                    )
                                    if reference_start < len(trans_line):
                                        reference = trans_line[reference_start:].strip()
                                else:
                                    # No digits after N, so N might be part of reference
                                    # Try to find reference starting from after N
                                    if len(type_code_remaining) > 0:
                                        reference = type_code_remaining.strip()
                            else:
                                # No "N" found, amount goes to end
                                amount_part = remaining
                                amount = float(amount_part.replace(",", "."))
                                if trans_line[j] == "D":
                                    amount = -amount  # Debit is negative

                            break

                    current_transaction = {
                        "transactiondate": transaction_date,
                        "amount": amount,
                        "accountNumber": account_number,
                        "currency": DEFAULT_CURRENCY,
                        "source_line": i
                        + 1,  # Line number (1-based) where transaction starts
                    }

                    # Store transaction type code and reference if extracted
                    if transaction_type_code:
                        current_transaction["transaction_type_code"] = (
                            transaction_type_code
                        )
                    if reference:
                        current_transaction["transaction_reference"] = reference

                except Exception:
                    # Log error but don't print to console in production
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(
                        f"Error parsing transaction line {i+1}: {line}", exc_info=True
                    )
                    current_transaction = {}

        # Description (:86:)
        elif line.startswith(":86:"):
            description = line[4:].strip()
            # Continue reading description lines until next tag
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(":"):
                description += " " + lines[i].strip()
                i += 1
            i -= 1  # Adjust for loop increment
            if current_transaction:
                current_transaction["description"] = description
                # Parse structured description
                try:
                    structured = parse_transaction_description(description)
                    if structured:
                        current_transaction["description_structured"] = json.dumps(
                            structured, ensure_ascii=False
                        )
                except Exception as e:
                    # If structured parsing fails, still keep the description
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"Failed to parse structured description: {e}", exc_info=True
                    )

        # Ending balance (:62F:)
        elif line.startswith(":62F:"):
            balance_str = line[5:].strip()
            if balance_str:
                try:
                    end_balance = float(balance_str.split("EUR")[1].replace(",", "."))
                except Exception:
                    pass
            # Save current transaction if it exists and has a description
            # Note: We require description to save transaction when encountering :62F: or new :61:
            if (
                current_transaction
                and "description" in current_transaction
                and current_transaction.get("description")
            ):
                current_transaction["startsaldo"] = start_balance
                current_transaction["endsaldo"] = end_balance
                current_transaction["valuedate"] = current_transaction.get(
                    "transactiondate"
                )
                current_transaction["mutationcode"] = ""
                if "currency" not in current_transaction:
                    current_transaction["currency"] = DEFAULT_CURRENCY
                transactions.append(current_transaction)
                current_transaction = {}

        # End of statement (-)
        elif line == "-":
            # Save current transaction if it exists and has a description
            if (
                current_transaction
                and "description" in current_transaction
                and current_transaction.get("description")
            ):
                current_transaction["startsaldo"] = start_balance
                current_transaction["endsaldo"] = end_balance
                current_transaction["valuedate"] = current_transaction.get(
                    "transactiondate"
                )
                current_transaction["mutationcode"] = ""
                if "currency" not in current_transaction:
                    current_transaction["currency"] = DEFAULT_CURRENCY
                transactions.append(current_transaction)
                current_transaction = {}

        i += 1

    # Add last transaction if exists (even without description, as it might be valid)
    if current_transaction and "transactiondate" in current_transaction:
        # Ensure description exists (even if empty) for transaction to be valid
        if "description" not in current_transaction:
            current_transaction["description"] = ""
        current_transaction["startsaldo"] = start_balance
        current_transaction["endsaldo"] = end_balance
        current_transaction["valuedate"] = current_transaction.get("transactiondate")
        current_transaction["mutationcode"] = ""
        if "currency" not in current_transaction:
            current_transaction["currency"] = DEFAULT_CURRENCY
        transactions.append(current_transaction)

    return transactions


def parse_mt940_file(file_path: Path) -> list[dict[str, Any]]:
    """Parse MT940 file and return list of transactions."""
    # Try using the parser library first, fallback to basic parser
    if PARSER_AVAILABLE and read_tsv is not None:
        try:
            # Try to use the library parser (may work for some formats)
            with open(file_path, encoding="utf-8") as f:
                # Check if it's TSV format (tab-separated)
                first_line = f.readline()
                f.seek(0)
                if "\t" in first_line:
                    # It's TSV format, use read_tsv
                    transactions_generator = read_tsv(f)
                    transactions = list(transactions_generator)

                    # Convert to standardized format
                    standardized = []
                    for trans in transactions:
                        if hasattr(trans, "_asdict"):
                            trans_dict = trans._asdict()
                        elif hasattr(trans, "__dict__"):
                            trans_dict = trans.__dict__
                        else:
                            trans_dict = trans if isinstance(trans, dict) else {}

                        description = str(trans_dict.get("description", ""))
                        standardized.append(
                            {
                                "accountNumber": str(
                                    trans_dict.get("accountNumber", "")
                                ),
                                "mutationcode": str(trans_dict.get("mutationcode", "")),
                                "transactiondate": parse_date(
                                    trans_dict.get("transactiondate", "")
                                ),
                                "valuedate": parse_date(
                                    trans_dict.get("valuedate", "")
                                ),
                                "startsaldo": parse_decimal(
                                    trans_dict.get("startsaldo", 0)
                                ),
                                "endsaldo": parse_decimal(
                                    trans_dict.get("endsaldo", 0)
                                ),
                                "amount": parse_decimal(trans_dict.get("amount", 0)),
                                "description": description,
                                "currency": trans_dict.get(
                                    "currency", DEFAULT_CURRENCY
                                ),
                                "source_line": trans_dict.get(
                                    "source_line"
                                ),  # Preserve source_line if present
                            }
                        )
                        # Parse structured description for standardized transactions
                        structured = parse_transaction_description(description)
                        if structured:
                            standardized[-1]["description_structured"] = json.dumps(
                                structured, ensure_ascii=False
                            )

                    return standardized
                else:
                    # It's MT940 format, use basic parser
                    return _parse_mt940_basic(file_path)
        except Exception:
            # Fallback to basic parser if library fails
            return _parse_mt940_basic(file_path)
    else:
        # Use basic parser if library not available
        return _parse_mt940_basic(file_path)
