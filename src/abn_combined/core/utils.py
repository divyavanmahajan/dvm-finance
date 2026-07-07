"""Shared normalization and hashing helpers (ported from abn-analyst)."""

from __future__ import annotations

import hashlib
import re
from typing import Any


def normalize_category(category: Any) -> str | None:
    """Normalize category to lowercase for storage.

    Handles comma-separated categories (e.g. "Food, Groceries" -> "food, groceries").
    Returns None for empty/whitespace-only input.
    """
    if category is None:
        return None
    if not isinstance(category, str):
        category = str(category)
    s = category.strip()
    if not s:
        return None
    parts = [p.strip().lower() for p in s.split(",") if p.strip()]
    return ", ".join(parts) if parts else None


def normalize_string_for_matching(value: Any) -> str:
    """Normalize string values for rule matching and hashing.

    Steps: None -> ""; str(); remove all whitespace; remove exact "WERO/"; lowercase.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    normalized = re.sub(r"\s+", "", value)
    normalized = normalized.replace("WERO/", "")
    return normalized.lower()


def calculate_transaction_hash_components(
    date_value: Any, description: Any, amount: Any, account: Any | None = None
) -> str:
    """Calculate a SHA256 hash from normalized transaction components (dup detection)."""
    if date_value:
        if hasattr(date_value, "isoformat"):
            date_str = date_value.isoformat()
        else:
            date_str = str(date_value)
    else:
        date_str = ""

    description_norm = normalize_string_for_matching(description)
    account_norm = normalize_string_for_matching(account)

    try:
        amount_float = float(amount) if amount is not None else 0.0
        amount_str = f"{amount_float:.2f}"
    except (ValueError, TypeError):
        amount_str = "0.00"

    hash_input = f"{account_norm}|{date_str}|{description_norm}|{amount_str}"
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
