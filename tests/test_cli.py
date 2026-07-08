"""CLI argument parsing and data-dir resolution tests."""

from __future__ import annotations

import pytest

from abn_combined.cli import build_parser, main
from abn_combined.settings import DATA_DIR_ENV, Settings, resolve_data_dir


def test_parser_defaults():
    args = build_parser().parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.data_dir is None
    assert args.command is None


def test_parser_overrides():
    args = build_parser().parse_args(["--host", "0.0.0.0", "--port", "9001", "--data-dir", "/tmp/x"])
    assert args.host == "0.0.0.0"
    assert args.port == 9001
    assert args.data_dir == "/tmp/x"


def test_migrate_legacy_subcommand():
    args = build_parser().parse_args(["migrate-legacy", "/path/to/abn_analyst.db"])
    assert args.command == "migrate-legacy"
    assert args.legacy_db == "/path/to/abn_analyst.db"


def test_migrate_legacy_data_dir_after_subcommand(tmp_path):
    """--data-dir placed AFTER the subcommand name resolves correctly."""
    args = build_parser().parse_args(
        ["migrate-legacy", "/path/to/db", "--data-dir", str(tmp_path)]
    )
    assert args.data_dir == str(tmp_path)


def test_migrate_legacy_data_dir_before_subcommand(tmp_path):
    """--data-dir placed BEFORE the subcommand name also resolves correctly."""
    args = build_parser().parse_args(
        ["--data-dir", str(tmp_path), "migrate-legacy", "/path/to/db"]
    )
    assert args.data_dir == str(tmp_path)


def test_migrate_legacy_missing_file_fails(capsys, tmp_path):
    rc = main(["--data-dir", str(tmp_path / "data"), "migrate-legacy", "/nope/abn_analyst.db"])
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_resolve_data_dir_explicit(tmp_path):
    assert resolve_data_dir(tmp_path / "d") == (tmp_path / "d").resolve()


def test_resolve_data_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "envdir"))
    assert resolve_data_dir(None) == (tmp_path / "envdir").resolve()


def test_resolve_data_dir_explicit_beats_env(monkeypatch, tmp_path):
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "envdir"))
    assert resolve_data_dir(tmp_path / "explicit") == (tmp_path / "explicit").resolve()


def test_resolve_data_dir_platform_default(monkeypatch):
    monkeypatch.delenv(DATA_DIR_ENV, raising=False)
    result = resolve_data_dir(None)
    assert "abn-combined" in str(result)


def test_ensure_data_dir_creates_subdirs(tmp_path):
    settings = Settings.create(data_dir=tmp_path / "data")
    settings.ensure_data_dir()
    assert settings.data_dir.is_dir()
    assert settings.statements_dir.is_dir()
    assert settings.snapshots_dir.is_dir()


def test_ensure_data_dir_unwritable_raises(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")
    settings = Settings.create(data_dir=blocker / "sub")
    with pytest.raises(RuntimeError, match="not writable"):
        settings.ensure_data_dir()
