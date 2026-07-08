"""Build a small legacy abn_analyst.db fixture for migration tests.

The DDL below is a verbatim copy of the schema of the REAL
``/Users/divya/projects/abn-analyst/abn_analyst.db`` (captured via read-only
``sqlite_master`` inspection). Note the trailing columns on ``transactions``
and ``categorization_rules`` — those were appended by the old ``ensure_*``
runtime migrations, so the column *order* differs from a fresh
``app/database.py`` ``create_all`` but the column *set* is identical.
Legacy rules have no ``uuid`` column (new in abn-combined).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

LEGACY_DDL = [
    """CREATE TABLE transactions (
        id VARCHAR NOT NULL,
        "accountNumber" VARCHAR NOT NULL,
        mutationcode VARCHAR,
        transactiondate DATE NOT NULL,
        valuedate DATE,
        startsaldo NUMERIC(15, 2),
        endsaldo NUMERIC(15, 2),
        amount NUMERIC(15, 2) NOT NULL,
        description VARCHAR,
        description_structured TEXT,
        category VARCHAR,
        currency VARCHAR(3) NOT NULL, categorization_source VARCHAR, source_file VARCHAR, source_line INTEGER, transaction_type_code VARCHAR, transaction_reference VARCHAR, manual_category VARCHAR, tags VARCHAR, manual_tags VARCHAR, transaction_hash VARCHAR(64),
        PRIMARY KEY (id)
    )""",
    """CREATE TABLE categorization_rules (
        id INTEGER NOT NULL,
        priority INTEGER NOT NULL,
        rule_type VARCHAR(50) NOT NULL,
        match_pattern VARCHAR(50) NOT NULL,
        field_target VARCHAR(50),
        match_value VARCHAR(500) NOT NULL,
        category VARCHAR(100) NOT NULL,
        is_active BOOLEAN,
        notes TEXT, tags VARCHAR, filter_account VARCHAR, filter_currency VARCHAR(3), filter_date_from DATE, filter_date_to DATE,
        PRIMARY KEY (id)
    )""",
    """CREATE TABLE rule_conditions (
        id INTEGER NOT NULL,
        rule_id INTEGER NOT NULL,
        field_target VARCHAR(50) NOT NULL,
        match_pattern VARCHAR(50) NOT NULL,
        match_value VARCHAR(500) NOT NULL,
        operator VARCHAR(3) NOT NULL,
        sort_order INTEGER NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(rule_id) REFERENCES categorization_rules (id) ON DELETE CASCADE
    )""",
    """CREATE TABLE budgets (
        id INTEGER NOT NULL,
        category VARCHAR(255) NOT NULL,
        amount NUMERIC(10, 2) NOT NULL,
        period VARCHAR(10) NOT NULL,
        start_date DATE,
        end_date DATE,
        notes TEXT,
        created_at DATE,
        updated_at DATE,
        PRIMARY KEY (id)
    )""",
    # Tables the migration must SKIP (auth / alembic bookkeeping).
    """CREATE TABLE users (
        id INTEGER NOT NULL,
        username VARCHAR(50) NOT NULL,
        email VARCHAR(100) NOT NULL,
        hashed_password VARCHAR(255) NOT NULL,
        full_name VARCHAR(100),
        role VARCHAR(20),
        is_active BOOLEAN,
        PRIMARY KEY (id)
    )""",
    """CREATE TABLE alembic_version (
        version_num VARCHAR(32) NOT NULL,
        CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
    )""",
]

TRANSACTIONS = [
    # (id, accountNumber, mutationcode, transactiondate, valuedate, startsaldo,
    #  endsaldo, amount, description, description_structured, category, currency,
    #  categorization_source, source_file, source_line, transaction_type_code,
    #  transaction_reference, manual_category, tags, manual_tags, transaction_hash)
    (
        "247141720_2025-12-02_-17.3_a398d38be5d2dc3e",
        "247141720",
        "GEA",
        "2025-12-02",
        "2025-12-02",
        1000.00,
        982.70,
        -17.30,
        "BEA, Betaalpas EDEKA MUENCHEN,PAS123",
        '{"merchant_name": "EDEKA MUENCHEN", "format": "BEA"}',
        "groceries-edeka",
        "EUR",
        "manual",
        "statements/dec.sta",
        14,
        "N426",
        "NONREF",
        "groceries-edeka",
        "supermarket",
        "edeka,germany",
        "aa11bb22cc33dd44",
    ),
    (
        "247141720_2025-12-16_-6.0_99629c729d0115d6",
        "247141720",
        "GEA",
        "2025-12-16",
        None,
        None,
        None,
        -6.00,
        "PARKING GARAGE CENTRUM",
        None,
        "nocategory",
        "EUR",
        "manual",
        None,
        None,
        None,
        None,
        "auto-parking",
        None,
        None,
        None,
    ),
    (
        "247141712_2025-12-26_-27687.0_6c586c98047981f7",
        "247141712",
        "OVB",
        "2025-12-26",
        "2025-12-27",
        50000.00,
        22313.00,
        -27687.00,
        "SEPA Overboeking IBAN: NL04ABNA0252265866 Naam: Mortgage BV",
        '{"iban": "NL04ABNA0252265866", "name": "Mortgage BV", "sepa_type": "Overboeking"}',
        "fixed-mortgage",
        "EUR",
        "manual",
        "statements/dec.sta",
        88,
        "N544",
        "REF001",
        "fixed-mortgage",
        None,
        None,
        "ee55ff66aa77bb88",
    ),
    (
        "247141720_2026-01-05_-42.5_1234567890abcdef",
        "247141720",
        "GEA",
        "2026-01-05",
        "2026-01-05",
        900.00,
        857.50,
        -42.50,
        "BEA, Betaalpas ALBERT HEIJN 1234",
        '{"merchant_name": "ALBERT HEIJN 1234", "format": "BEA"}',
        "groceries",
        "EUR",
        "42",
        "statements/jan.sta",
        3,
        "N426",
        "NONREF",
        None,
        "supermarket",
        None,
        "1122334455667788",
    ),
    (
        "247141720_2026-02-01_2500.0_fedcba0987654321",
        "247141720",
        "SAL",
        "2026-02-01",
        "2026-02-01",
        857.50,
        3357.50,
        2500.00,
        "SEPA Salaris werkgever",
        None,
        None,
        "EUR",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    ),
]

RULES = [
    # (id, priority, rule_type, match_pattern, field_target, match_value,
    #  category, is_active, notes, tags, filter_account, filter_currency,
    #  filter_date_from, filter_date_to)
    (
        9,
        6,
        "account_iban",
        "exact",
        "iban",
        "NL04ABNA0252265866",
        "transfer",
        1,
        "IBAN: NL04ABNA0252265866",
        None,
        None,
        None,
        None,
        None,
    ),
    (
        42,
        10,
        "keyword",
        "contains",
        "description",
        "ALBERT HEIJN",
        "groceries",
        1,
        None,
        "supermarket",
        "247141720",
        "EUR",
        "2024-01-01",
        None,
    ),
    (
        120,
        99,
        "structured_field",
        "regex",
        "merchant_name",
        r"^EDEKA.*",
        "groceries-edeka",
        0,
        "inactive edeka rule",
        None,
        None,
        None,
        None,
        None,
    ),
]

RULE_CONDITIONS = [
    # (id, rule_id, field_target, match_pattern, match_value, operator, sort_order)
    (1, 42, "merchant_name", "contains", "HEIJN", "AND", 0),
    (2, 42, "description", "starts_with", "BEA", "OR", 1),
]

BUDGETS = [
    # (id, category, amount, period, start_date, end_date, notes, created_at, updated_at)
    (1, "groceries", 1500, "month", None, None, None, "2026-01-12", "2026-01-12"),
    (2, "dining", 200, "month", "2026-01-01", "2026-12-31", "eat less", "2026-01-12", "2026-02-01"),
]


def create_legacy_db(path: Path, *, with_data: bool = True) -> Path:
    """Create a legacy-schema SQLite DB at *path*; optionally seed sample rows."""
    conn = sqlite3.connect(path)
    try:
        for ddl in LEGACY_DDL:
            conn.execute(ddl)
        if with_data:
            conn.executemany(
                "INSERT INTO transactions VALUES (" + ",".join("?" * 21) + ")",
                TRANSACTIONS,
            )
            conn.executemany(
                "INSERT INTO categorization_rules VALUES (" + ",".join("?" * 14) + ")",
                RULES,
            )
            conn.executemany(
                "INSERT INTO rule_conditions VALUES (?,?,?,?,?,?,?)", RULE_CONDITIONS
            )
            conn.executemany(
                "INSERT INTO budgets VALUES (?,?,?,?,?,?,?,?,?)", BUDGETS
            )
            conn.execute(
                "INSERT INTO users VALUES (1,'admin','admin@example.com','x','Admin','admin',1)"
            )
            conn.execute("INSERT INTO alembic_version VALUES ('abc123def456')")
        conn.commit()
    finally:
        conn.close()
    return path
