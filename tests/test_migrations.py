"""Startup migration tests."""

from __future__ import annotations

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from abn_combined.migrations import _alembic_config, upgrade_to_head
from abn_combined.settings import Settings

EXPECTED_TABLES = {
    "transactions",
    "categorization_rules",
    "rule_conditions",
    "budgets",
    "rule_change_reports",
    "rule_change_items",
    "download_state",
    "snapshot_imports",
    "merge_reports",
}


def _head_revision(settings: Settings) -> str:
    script = ScriptDirectory.from_config(_alembic_config(settings))
    return script.get_current_head()


def _current_revision(settings: Settings) -> str | None:
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def test_fresh_startup_creates_all_tables(tmp_path):
    settings = Settings.create(data_dir=tmp_path / "data")
    settings.ensure_data_dir()
    upgrade_to_head(settings)

    engine = create_engine(settings.database_url)
    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables)


def test_alembic_current_is_head(tmp_path):
    settings = Settings.create(data_dir=tmp_path / "data")
    settings.ensure_data_dir()
    upgrade_to_head(settings)
    assert _current_revision(settings) == _head_revision(settings)


def test_second_startup_is_noop(tmp_path):
    settings = Settings.create(data_dir=tmp_path / "data")
    settings.ensure_data_dir()
    upgrade_to_head(settings)
    rev1 = _current_revision(settings)
    # Running again must not error and must leave the revision unchanged.
    upgrade_to_head(settings)
    assert _current_revision(settings) == rev1


# ---------------------------------------------------------------------------
# The reference column and the merge column (c81a4f73be20)
# ---------------------------------------------------------------------------

_PREVIOUS_REVISION = "b3c1f0a27d44"
_REFERENCE_REVISION = "c81a4f73be20"


def _upgrade_to(settings: Settings, revision: str) -> None:
    from alembic import command

    command.upgrade(_alembic_config(settings), revision)


def _downgrade_to(settings: Settings, revision: str) -> None:
    from alembic import command

    command.downgrade(_alembic_config(settings), revision)


def _settings_at_previous_revision(tmp_path) -> Settings:
    """Build a database at the revision before the two new columns."""
    settings = Settings.create(data_dir=tmp_path / "data")
    settings.ensure_data_dir()
    _upgrade_to(settings, _PREVIOUS_REVISION)
    return settings


def _insert_row(settings: Settings, row_id: str, structured: str | None) -> None:
    from sqlalchemy import text

    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transactions "
                "(id, accountNumber, transactiondate, amount, description, "
                "description_structured, currency, is_manual) "
                "VALUES (:id, '720317081', '2024-05-19', -5.75, 'x', :st, "
                "'EUR', 0)"
            ),
            {"id": row_id, "st": structured},
        )


def _reference_of(settings: Settings, row_id: str) -> str | None:
    from sqlalchemy import text

    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT end_to_end_reference FROM transactions WHERE id = :id"),
            {"id": row_id},
        ).scalar()


def test_reference_migration_adds_both_columns(tmp_path):
    """Task 4.3: the upgrade adds the two columns and their indexes."""
    settings = Settings.create(data_dir=tmp_path / "data")
    settings.ensure_data_dir()
    upgrade_to_head(settings)

    engine = create_engine(settings.database_url)
    columns = {c["name"] for c in inspect(engine).get_columns("transactions")}
    assert {"end_to_end_reference", "merged_into"}.issubset(columns)

    indexes = {i["name"] for i in inspect(engine).get_indexes("transactions")}
    assert "ix_transactions_end_to_end_reference" in indexes
    assert "ix_transactions_merged_into" in indexes


def test_reference_migration_downgrade_drops_both_columns(tmp_path):
    """Task 4.3: the downgrade runs and removes the two columns."""
    settings = Settings.create(data_dir=tmp_path / "data")
    settings.ensure_data_dir()
    upgrade_to_head(settings)
    _downgrade_to(settings, _PREVIOUS_REVISION)

    engine = create_engine(settings.database_url)
    columns = {c["name"] for c in inspect(engine).get_columns("transactions")}
    assert "end_to_end_reference" not in columns
    assert "merged_into" not in columns


def test_backfill_reads_the_canonical_key(tmp_path):
    """Task 4.4: a row from before the change keeps its reference."""
    settings = _settings_at_previous_revision(tmp_path)
    _insert_row(
        settings,
        "canonical",
        '{"format": "sepa", "end_to_end_reference": "KFF5Q4D85TQK39G6"}',
    )
    _upgrade_to(settings, _REFERENCE_REVISION)

    assert _reference_of(settings, "canonical") == "KFF5Q4D85TQK39G6"


def test_backfill_reads_the_old_labelled_key(tmp_path):
    """Task 4.4: the backfill also reads the old key of the labelled parser."""
    settings = _settings_at_previous_revision(tmp_path)
    _insert_row(
        settings, "old", '{"format": "sepa", "reference": "ABCD1234EFGH"}'
    )
    _upgrade_to(settings, _REFERENCE_REVISION)

    assert _reference_of(settings, "old") == "ABCD1234EFGH"


def test_backfill_leaves_a_row_without_a_reference(tmp_path):
    """Task 4.4: a row with no reference keeps an empty column."""
    settings = _settings_at_previous_revision(tmp_path)
    _insert_row(settings, "pos", '{"format": "pos", "merchant_name": "JUMBO"}')
    _insert_row(settings, "none", None)
    _upgrade_to(settings, _REFERENCE_REVISION)

    assert _reference_of(settings, "pos") is None
    assert _reference_of(settings, "none") is None


def test_backfill_skips_a_sentinel_reference(tmp_path):
    """Task 5.3: the column means a usable reference on each write path.

    `insert_transactions` stores no sentinel, so the backfill must store none
    either. `tests/fixtures/mt940_sample.STA` holds `NOTPROVIDED` 136 times.
    """
    settings = _settings_at_previous_revision(tmp_path)
    _insert_row(
        settings, "sentinel", '{"format": "sepa", "reference": "NOTPROVIDED"}'
    )
    _insert_row(
        settings,
        "split",
        '{"format": "sepa", "end_to_end_reference": "NOTP ROVIDED"}',
    )
    _insert_row(settings, "nonref", '{"format": "sepa", "reference": "NONREF"}')
    _insert_row(
        settings, "real", '{"format": "sepa", "reference": "KFF5Q4D85TQK39G6"}'
    )
    _upgrade_to(settings, _REFERENCE_REVISION)

    assert _reference_of(settings, "sentinel") is None
    assert _reference_of(settings, "split") is None
    assert _reference_of(settings, "nonref") is None
    assert _reference_of(settings, "real") == "KFF5Q4D85TQK39G6"


# ---------------------------------------------------------------------------
# Several budgets for one category and period (e4b7d2a91c36)
# ---------------------------------------------------------------------------


def test_two_budgets_for_one_pair_store_after_upgrade(tmp_path):
    from sqlalchemy import text

    settings = Settings.create(data_dir=tmp_path / "data")
    settings.ensure_data_dir()
    upgrade_to_head(settings)

    engine = create_engine(settings.database_url)
    indexes = {i["name"]: i for i in inspect(engine).get_indexes("budgets")}
    assert not indexes["idx_budgets_category_period"]["unique"]
    with engine.begin() as conn:
        for start, end in (("2026-07-01", "2026-10-31"), ("2026-11-01", None)):
            conn.execute(
                text("INSERT INTO budgets (category, amount, period, start_date, end_date)"
                     " VALUES ('food', 100, 'month', :s, :e)"),
                {"s": start, "e": end},
            )
        count = conn.execute(text("SELECT count(*) FROM budgets")).scalar()
    assert count == 2
