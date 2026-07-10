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
