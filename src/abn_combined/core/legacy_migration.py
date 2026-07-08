"""One-time migration from a legacy abn_analyst.db (spec FR10).

Opens the legacy SQLite file strictly read-only (sqlite URI ``mode=ro``) and
copies transactions, categorization rules (+ freshly generated UUIDs),
rule conditions, and budgets into the abn-combined database. Users/auth and
alembic bookkeeping tables are ignored. The whole run is one destination
transaction: on any failure nothing is written. Re-runs skip rows whose ids
already exist and count them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..logging_config import get_logger
from ..settings import Settings
from .models import Budget, CategorizationRule, RuleCondition, Transaction

logger = get_logger(__name__)


class LegacyMigrationError(Exception):
    """The legacy database is missing, unreadable, or an unknown schema variant."""


#: Tables the migration copies, with the columns each must have. This matches
#: the real ``abn_analyst.db`` schema (verified read-only against the live
#: file); anything missing means an unknown/older schema variant → refuse.
REQUIRED_SCHEMA: dict[str, set[str]] = {
    "transactions": {
        "id",
        "accountNumber",
        "mutationcode",
        "transactiondate",
        "valuedate",
        "startsaldo",
        "endsaldo",
        "amount",
        "description",
        "description_structured",
        "category",
        "manual_category",
        "tags",
        "manual_tags",
        "categorization_source",
        "currency",
        "source_file",
        "source_line",
        "transaction_type_code",
        "transaction_reference",
        "transaction_hash",
    },
    "categorization_rules": {
        "id",
        "priority",
        "rule_type",
        "match_pattern",
        "field_target",
        "match_value",
        "category",
        "tags",
        "is_active",
        "notes",
        "filter_account",
        "filter_currency",
        "filter_date_from",
        "filter_date_to",
    },
    "rule_conditions": {
        "id",
        "rule_id",
        "field_target",
        "match_pattern",
        "match_value",
        "operator",
        "sort_order",
    },
    "budgets": {
        "id",
        "category",
        "amount",
        "period",
        "start_date",
        "end_date",
        "notes",
        "created_at",
        "updated_at",
    },
}

#: Legacy tables intentionally NOT migrated.
SKIPPED_TABLES = ("users", "alembic_version")


@dataclass
class TableResult:
    inserted: int = 0
    skipped: int = 0


@dataclass
class MigrationSummary:
    tables: dict[str, TableResult] = field(default_factory=dict)

    @property
    def total_inserted(self) -> int:
        return sum(t.inserted for t in self.tables.values())

    @property
    def total_skipped(self) -> int:
        return sum(t.skipped for t in self.tables.values())

    def format(self) -> str:
        lines = ["Legacy migration summary:"]
        for name, result in self.tables.items():
            lines.append(
                f"  {name:<22} inserted {result.inserted:>6}   skipped {result.skipped:>6}"
            )
        lines.append(
            f"  {'TOTAL':<22} inserted {self.total_inserted:>6}   "
            f"skipped {self.total_skipped:>6}"
        )
        return "\n".join(lines)


def _open_legacy_read_only(legacy_path: Path):
    """Return an engine for the legacy DB opened strictly read-only."""
    if not legacy_path.is_file():
        raise LegacyMigrationError(f"Legacy database not found: {legacy_path}")
    # sqlite URI with mode=ro: the file is never opened for writing.
    url = f"sqlite:///file:{legacy_path}?mode=ro&uri=true"
    return create_engine(url)


def _reflect_and_validate(conn: Connection) -> dict[str, Table]:
    metadata = MetaData()
    try:
        metadata.reflect(bind=conn)
    except SQLAlchemyError as exc:  # pragma: no cover - corrupt file paths vary
        raise LegacyMigrationError(f"Could not read legacy database: {exc}") from exc

    tables: dict[str, Table] = {}
    problems: list[str] = []
    for name, required_cols in REQUIRED_SCHEMA.items():
        table = metadata.tables.get(name)
        if table is None:
            problems.append(f"missing table {name!r}")
            continue
        missing = required_cols - {c.name for c in table.columns}
        if missing:
            problems.append(f"table {name!r} missing columns: {sorted(missing)}")
        tables[name] = table
    if problems:
        raise LegacyMigrationError(
            "Unknown legacy schema variant — refusing to migrate ("
            + "; ".join(problems)
            + "). Expected the abn_analyst.db schema."
        )
    return tables


def _as_date(value: Any) -> date | None:
    """Coerce legacy DATE storage (ISO string / datetime / date) to date."""
    if value is None or isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _existing_ids(db: Session, column) -> set:
    return set(db.scalars(select(column)))


def _copy_transactions(db: Session, rows: list[dict], result: TableResult) -> None:
    existing = _existing_ids(db, Transaction.id)
    for row in rows:
        if row["id"] in existing:
            result.skipped += 1
            continue
        db.add(
            Transaction(
                id=row["id"],
                accountNumber=row["accountNumber"],
                mutationcode=row["mutationcode"],
                transactiondate=_as_date(row["transactiondate"]),
                valuedate=_as_date(row["valuedate"]),
                startsaldo=row["startsaldo"],
                endsaldo=row["endsaldo"],
                amount=row["amount"],
                description=row["description"],
                description_structured=row["description_structured"],
                category=row["category"],
                manual_category=row["manual_category"],
                tags=row["tags"],
                manual_tags=row["manual_tags"],
                categorization_source=row["categorization_source"],
                currency=row["currency"],
                source_file=row["source_file"],
                source_line=row["source_line"],
                transaction_type_code=row["transaction_type_code"],
                transaction_reference=row["transaction_reference"],
                transaction_hash=row["transaction_hash"],
            )
        )
        result.inserted += 1


def _copy_rules(db: Session, rows: list[dict], result: TableResult) -> None:
    existing = _existing_ids(db, CategorizationRule.id)
    for row in rows:
        if row["id"] in existing:
            result.skipped += 1
            continue
        db.add(
            CategorizationRule(
                id=row["id"],  # preserve numeric id: transactions reference it
                uuid=str(uuid.uuid4()),  # legacy rules have no uuid column
                priority=row["priority"],
                rule_type=row["rule_type"],
                match_pattern=row["match_pattern"],
                field_target=row["field_target"],
                match_value=row["match_value"],
                category=row["category"],
                tags=row["tags"],
                is_active=bool(row["is_active"]) if row["is_active"] is not None else True,
                notes=row["notes"],
                filter_account=row["filter_account"],
                filter_currency=row["filter_currency"],
                filter_date_from=_as_date(row["filter_date_from"]),
                filter_date_to=_as_date(row["filter_date_to"]),
            )
        )
        result.inserted += 1


def _copy_rule_conditions(db: Session, rows: list[dict], result: TableResult) -> None:
    existing = _existing_ids(db, RuleCondition.id)
    for row in rows:
        if row["id"] in existing:
            result.skipped += 1
            continue
        db.add(
            RuleCondition(
                id=row["id"],
                rule_id=row["rule_id"],
                field_target=row["field_target"],
                match_pattern=row["match_pattern"],
                match_value=row["match_value"],
                operator=row["operator"],
                sort_order=row["sort_order"],
            )
        )
        result.inserted += 1


def _copy_budgets(db: Session, rows: list[dict], result: TableResult) -> None:
    existing = _existing_ids(db, Budget.id)
    for row in rows:
        if row["id"] in existing:
            result.skipped += 1
            continue
        db.add(
            Budget(
                id=row["id"],
                category=row["category"],
                amount=row["amount"],
                period=row["period"],
                start_date=_as_date(row["start_date"]),
                end_date=_as_date(row["end_date"]),
                notes=row["notes"],
                created_at=_as_date(row["created_at"]),
                updated_at=_as_date(row["updated_at"]),
            )
        )
        result.inserted += 1


def migrate_legacy(legacy_path: Path | str, settings: Settings) -> MigrationSummary:
    """Copy all legacy data into the settings-bound abn-combined database.

    Idempotent: rows whose ids already exist are skipped and counted. The whole
    run is a single destination transaction — any failure rolls back everything.
    """
    from ..db import configure_engine, get_session_factory
    from ..migrations import upgrade_to_head

    legacy_path = Path(legacy_path)
    legacy_engine = _open_legacy_read_only(legacy_path)

    # Read everything from the legacy DB up-front (read-only connection).
    try:
        with legacy_engine.connect() as legacy_conn:
            tables = _reflect_and_validate(legacy_conn)
            legacy_rows = {
                name: [dict(r) for r in legacy_conn.execute(select(table)).mappings()]
                for name, table in tables.items()
            }
    finally:
        legacy_engine.dispose()

    # Prepare the destination (create data dir + run alembic to head).
    settings.ensure_data_dir()
    configure_engine(settings)
    upgrade_to_head(settings)

    summary = MigrationSummary(
        tables={name: TableResult() for name in REQUIRED_SCHEMA}
    )

    session_factory = get_session_factory()
    with session_factory() as db:
        try:
            _copy_transactions(db, legacy_rows["transactions"], summary.tables["transactions"])
            _copy_rules(
                db, legacy_rows["categorization_rules"], summary.tables["categorization_rules"]
            )
            _copy_rule_conditions(
                db, legacy_rows["rule_conditions"], summary.tables["rule_conditions"]
            )
            _copy_budgets(db, legacy_rows["budgets"], summary.tables["budgets"])
            db.commit()
        except Exception:
            db.rollback()
            raise

    logger.info(
        "legacy_migration_done",
        source=str(legacy_path),
        inserted=summary.total_inserted,
        skipped=summary.total_skipped,
    )
    return summary
