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
