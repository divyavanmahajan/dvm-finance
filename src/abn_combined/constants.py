"""Application constants for transfer exclusion and filtering.

This module defines transfer-related categories and helper functions to
consistently identify transfer transactions across the application.
"""

from __future__ import annotations

# Transfer categories to exclude by default
# These represent inter-account movements and should not count as income/expense
TRANSFER_CATEGORIES = [
    'transfer',
    'transfer-paypal',
]

# The reserved pseudo account of each hand-entered transaction.
# No parser, no downloader, and no import writes a transaction to this account.
CASH_ACCOUNT = 'CASH'


def is_reserved_account(account: str | None) -> bool:
    """Check if the account is the reserved pseudo account.

    Args:
        account: The account identifier to check (may be None)

    Returns:
        True if the account is the reserved pseudo account, False otherwise
    """
    if not account:
        return False
    return str(account).strip().upper() == CASH_ACCOUNT


def is_transfer_category(category: str | None) -> bool:
    """Check if a category represents a transfer (inter-account movement).

    Args:
        category: The category string to check (may be None)

    Returns:
        True if the category is a transfer or starts with 'transfer-', False otherwise
    """
    if not category:
        return False
    category_lower = category.lower()
    return category_lower in TRANSFER_CATEGORIES or category_lower.startswith('transfer-')
