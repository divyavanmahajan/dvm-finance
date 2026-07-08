"""Tests for the legacy abn_analyst.db migration (step 12, spec FR10)."""

from __future__ import annotations

import json
import re
from datetime import date

import pytest
from sqlalchemy import select

import abn_combined.core.legacy_migration as lm
from abn_combined.cli import main
from abn_combined.core.legacy_migration import LegacyMigrationError, migrate_legacy
from abn_combined.core.models import Budget, CategorizationRule, RuleCondition, Transaction

from .fixtures.legacy_fixture import (
    BUDGETS,
    RULE_CONDITIONS,
    RULES,
    TRANSACTIONS,
    create_legacy_db,
)


@pytest.fixture
def legacy_db(tmp_path):
    return create_legacy_db(tmp_path / "abn_analyst.db")


@pytest.fixture
def dest_session(settings):
    """A session factory bound to the destination DB (schema created)."""
    from abn_combined.db import configure_engine, get_session_factory
    from abn_combined.migrations import upgrade_to_head

    settings.ensure_data_dir()
    configure_engine(settings)
    upgrade_to_head(settings)
    return get_session_factory()


def test_full_copy_counts(legacy_db, settings, dest_session):
    summary = migrate_legacy(legacy_db, settings)

    assert summary.tables["transactions"].inserted == len(TRANSACTIONS)
    assert summary.tables["transactions"].skipped == 0
    assert summary.tables["categorization_rules"].inserted == len(RULES)
    assert summary.tables["rule_conditions"].inserted == len(RULE_CONDITIONS)
    assert summary.tables["budgets"].inserted == len(BUDGETS)

    with dest_session() as db:
        assert db.scalar(select(Transaction.id).where(Transaction.id == TRANSACTIONS[0][0]))
        assert len(db.scalars(select(Transaction)).all()) == len(TRANSACTIONS)
        assert len(db.scalars(select(CategorizationRule)).all()) == len(RULES)
        assert len(db.scalars(select(RuleCondition)).all()) == len(RULE_CONDITIONS)
        assert len(db.scalars(select(Budget)).all()) == len(BUDGETS)


def test_field_fidelity_transactions(legacy_db, settings, dest_session):
    migrate_legacy(legacy_db, settings)
    with dest_session() as db:
        # Manual category + tags + source preserved byte-for-byte.
        txn = db.get(Transaction, "247141720_2025-12-02_-17.3_a398d38be5d2dc3e")
        assert txn.manual_category == "groceries-edeka"
        assert txn.manual_tags == "edeka,germany"
        assert txn.tags == "supermarket"
        assert txn.categorization_source == "manual"
        assert txn.transactiondate == date(2025, 12, 2)
        assert txn.valuedate == date(2025, 12, 2)
        assert float(txn.amount) == -17.30
        assert json.loads(txn.description_structured)["merchant_name"] == "EDEKA MUENCHEN"
        assert txn.source_file == "statements/dec.sta"
        assert txn.source_line == 14
        assert txn.transaction_hash == "aa11bb22cc33dd44"

        # Manual override differing from rule category preserved.
        txn2 = db.get(Transaction, "247141720_2025-12-16_-6.0_99629c729d0115d6")
        assert txn2.category == "nocategory"
        assert txn2.manual_category == "auto-parking"

        # Rule-id categorization_source preserved as string.
        txn3 = db.get(Transaction, "247141720_2026-01-05_-42.5_1234567890abcdef")
        assert txn3.categorization_source == "42"

        # Fully NULL optional columns survive.
        txn4 = db.get(Transaction, "247141720_2026-02-01_2500.0_fedcba0987654321")
        assert txn4.category is None
        assert txn4.categorization_source is None
        assert float(txn4.amount) == 2500.0


def test_field_fidelity_rules_conditions_budgets(legacy_db, settings, dest_session):
    migrate_legacy(legacy_db, settings)
    with dest_session() as db:
        rule = db.get(CategorizationRule, 42)
        assert rule is not None, "numeric rule id must be preserved"
        assert rule.priority == 10
        assert rule.rule_type == "keyword"
        assert rule.match_pattern == "contains"
        assert rule.match_value == "ALBERT HEIJN"
        assert rule.category == "groceries"
        assert rule.tags == "supermarket"
        assert rule.filter_account == "247141720"
        assert rule.filter_currency == "EUR"
        assert rule.filter_date_from == date(2024, 1, 1)
        assert rule.filter_date_to is None
        assert rule.is_active is True

        inactive = db.get(CategorizationRule, 120)
        assert inactive.is_active is False
        assert inactive.match_pattern == "regex"
        assert inactive.match_value == r"^EDEKA.*"

        # Every migrated rule gets a unique UUID.
        uuids = [r.uuid for r in db.scalars(select(CategorizationRule)).all()]
        assert all(u and len(u) == 36 for u in uuids)
        assert len(set(uuids)) == len(uuids)

        # Conditions keep their rule linkage, operator and order.
        conds = db.scalars(
            select(RuleCondition).where(RuleCondition.rule_id == 42).order_by(RuleCondition.sort_order)
        ).all()
        assert [(c.field_target, c.match_pattern, c.match_value, c.operator, c.sort_order) for c in conds] == [
            ("merchant_name", "contains", "HEIJN", "AND", 0),
            ("description", "starts_with", "BEA", "OR", 1),
        ]

        budget = db.get(Budget, 2)
        assert budget.category == "dining"
        assert float(budget.amount) == 200.0
        assert budget.period == "month"
        assert budget.start_date == date(2026, 1, 1)
        assert budget.end_date == date(2026, 12, 31)
        assert budget.notes == "eat less"


def test_idempotent_rerun(legacy_db, settings, dest_session):
    first = migrate_legacy(legacy_db, settings)
    assert first.tables["transactions"].inserted == len(TRANSACTIONS)

    second = migrate_legacy(legacy_db, settings)
    for table, result in second.tables.items():
        assert result.inserted == 0, f"{table} inserted rows on re-run"
    assert second.tables["transactions"].skipped == len(TRANSACTIONS)
    assert second.tables["categorization_rules"].skipped == len(RULES)
    assert second.tables["rule_conditions"].skipped == len(RULE_CONDITIONS)
    assert second.tables["budgets"].skipped == len(BUDGETS)

    with dest_session() as db:
        assert len(db.scalars(select(Transaction)).all()) == len(TRANSACTIONS)
        # UUIDs unchanged by the re-run (no rewrite of existing rules).
        rule = db.get(CategorizationRule, 42)
        uuid_before = rule.uuid
    migrate_legacy(legacy_db, settings)
    with dest_session() as db:
        assert db.get(CategorizationRule, 42).uuid == uuid_before


def test_unknown_schema_rejected(tmp_path, settings, dest_session):
    import sqlite3

    bogus = tmp_path / "not_legacy.db"
    conn = sqlite3.connect(bogus)
    conn.execute("CREATE TABLE something_else (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    with pytest.raises(LegacyMigrationError, match="[Uu]nknown|[Mm]issing"):
        migrate_legacy(bogus, settings)

    with dest_session() as db:
        assert db.scalars(select(Transaction)).all() == []


def test_missing_columns_rejected(tmp_path, settings, dest_session):
    """A transactions table without the manual_* columns is an unknown variant."""
    import sqlite3

    old_variant = tmp_path / "old_variant.db"
    conn = sqlite3.connect(old_variant)
    conn.execute(
        'CREATE TABLE transactions (id VARCHAR PRIMARY KEY, "accountNumber" VARCHAR, '
        "transactiondate DATE, amount NUMERIC)"
    )
    conn.execute(
        "CREATE TABLE categorization_rules (id INTEGER PRIMARY KEY, priority INTEGER)"
    )
    conn.commit()
    conn.close()

    with pytest.raises(LegacyMigrationError):
        migrate_legacy(old_variant, settings)


def test_missing_file_rejected(tmp_path, settings):
    with pytest.raises(LegacyMigrationError, match="not found|does not exist"):
        migrate_legacy(tmp_path / "nope.db", settings)


def test_transactional_no_partial_writes(legacy_db, settings, dest_session, monkeypatch):
    """If any table copy fails mid-run, nothing at all is written."""

    def boom(*args, **kwargs):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(lm, "_copy_budgets", boom)

    with pytest.raises(RuntimeError, match="injected failure"):
        migrate_legacy(legacy_db, settings)

    with dest_session() as db:
        assert db.scalars(select(Transaction)).all() == []
        assert db.scalars(select(CategorizationRule)).all() == []
        assert db.scalars(select(RuleCondition)).all() == []


def test_legacy_db_opened_read_only(legacy_db, settings, dest_session):
    """The migration must not write to the legacy file (mtime/content unchanged)."""
    before = legacy_db.read_bytes()
    migrate_legacy(legacy_db, settings)
    assert legacy_db.read_bytes() == before


class TestFirstRunHint:
    def test_empty_db_shows_migrate_hint(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "migrate-legacy" in resp.text

    def test_hint_hidden_when_filters_active(self, client):
        resp = client.get("/?q=nomatchxyz")
        assert resp.status_code == 200
        assert "migrate-legacy" not in resp.text
        assert "No transactions match" in resp.text

    def test_hint_hidden_when_data_present(self, legacy_db, settings, dest_session):
        from fastapi.testclient import TestClient

        from abn_combined.app import create_app

        migrate_legacy(legacy_db, settings)
        with TestClient(create_app(settings)) as client:
            resp = client.get("/")
            assert "migrate-legacy" not in resp.text
            assert "Showing" in resp.text


class TestCli:
    def test_cli_success_prints_summary(self, tmp_path, capsys):
        legacy = create_legacy_db(tmp_path / "abn_analyst.db")
        data_dir = tmp_path / "data"

        rc = main(["--data-dir", str(data_dir), "migrate-legacy", str(legacy)])

        assert rc == 0
        out = capsys.readouterr().out
        assert "transactions" in out
        assert "categorization_rules" in out
        assert "rule_conditions" in out
        assert "budgets" in out
        assert str(len(TRANSACTIONS)) in out

    def test_cli_rerun_reports_skipped(self, tmp_path, capsys):
        legacy = create_legacy_db(tmp_path / "abn_analyst.db")
        data_dir = tmp_path / "data"
        assert main(["--data-dir", str(data_dir), "migrate-legacy", str(legacy)]) == 0
        capsys.readouterr()
        assert main(["--data-dir", str(data_dir), "migrate-legacy", str(legacy)]) == 0
        out = capsys.readouterr().out
        assert re.search(r"transactions\s+inserted\s+0\s+skipped\s+5", out)

    def test_cli_unknown_schema_exits_nonzero(self, tmp_path, capsys):
        import sqlite3

        bogus = tmp_path / "bogus.db"
        conn = sqlite3.connect(bogus)
        conn.execute("CREATE TABLE x (id INTEGER)")
        conn.commit()
        conn.close()

        rc = main(["--data-dir", str(tmp_path / "data"), "migrate-legacy", str(bogus)])
        assert rc != 0
        assert capsys.readouterr().err.strip()

    def test_cli_missing_file_exits_nonzero(self, tmp_path, capsys):
        rc = main(
            ["--data-dir", str(tmp_path / "data"), "migrate-legacy", str(tmp_path / "nope.db")]
        )
        assert rc != 0
        assert capsys.readouterr().err.strip()
