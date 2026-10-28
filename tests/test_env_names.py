"""The environment variables carry the prefix `DVM_FINANCE_`.

The project used the name `abn-combined` before. The application therefore
still reads the old name of each variable, and it warns about it.
"""

from __future__ import annotations

import pytest

from abn_combined import settings as settings_mod
from abn_combined.settings import (
    DATA_DIR_ENV,
    LEGACY_ENV_NAMES,
    LOG_ENV,
    NO_BROWSER_ENV,
    Settings,
    read_env,
    resolve_data_dir,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove each name, and forget each warning of an earlier test."""
    for new_name, old_name in LEGACY_ENV_NAMES.items():
        monkeypatch.delenv(new_name, raising=False)
        monkeypatch.delenv(old_name, raising=False)
    settings_mod._WARNED.clear()
    yield
    settings_mod._WARNED.clear()


# --- the table -------------------------------------------------------------


def test_each_variable_carries_the_new_prefix() -> None:
    assert DATA_DIR_ENV == "DVM_FINANCE_DATA_DIR"
    assert NO_BROWSER_ENV == "DVM_FINANCE_NO_BROWSER"
    assert LOG_ENV == "DVM_FINANCE_LOG_ENV"


def test_the_table_covers_each_variable_that_the_code_reads() -> None:
    """A variable that the table does not hold loses its old name in silence."""
    assert set(LEGACY_ENV_NAMES) == {DATA_DIR_ENV, NO_BROWSER_ENV, LOG_ENV}
    for new_name, old_name in LEGACY_ENV_NAMES.items():
        assert new_name.startswith("DVM_FINANCE_")
        assert old_name.startswith("ABN_COMBINED_")
        assert new_name.removeprefix("DVM_FINANCE_") == old_name.removeprefix(
            "ABN_COMBINED_"
        )


# --- the helper ------------------------------------------------------------


def test_the_helper_reads_the_new_name(monkeypatch) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, "/new")
    assert read_env(DATA_DIR_ENV) == "/new"


def test_the_helper_reads_the_old_name(monkeypatch) -> None:
    monkeypatch.setenv(LEGACY_ENV_NAMES[DATA_DIR_ENV], "/old")
    assert read_env(DATA_DIR_ENV) == "/old"


def test_the_new_name_wins_over_the_old_name(monkeypatch) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, "/new")
    monkeypatch.setenv(LEGACY_ENV_NAMES[DATA_DIR_ENV], "/old")
    assert read_env(DATA_DIR_ENV) == "/new"


def test_the_helper_returns_the_default_with_neither_name() -> None:
    assert read_env(LOG_ENV, "development") == "development"
    assert read_env(DATA_DIR_ENV) is None


# --- the warning -----------------------------------------------------------


def test_the_old_name_writes_a_warning_that_names_both(monkeypatch, capsys) -> None:
    monkeypatch.setenv(LEGACY_ENV_NAMES[DATA_DIR_ENV], "/old")
    read_env(DATA_DIR_ENV)
    err = capsys.readouterr().err
    assert "ABN_COMBINED_DATA_DIR" in err
    assert "DVM_FINANCE_DATA_DIR" in err


def test_the_warning_appears_one_time_for_each_name(monkeypatch, capsys) -> None:
    monkeypatch.setenv(LEGACY_ENV_NAMES[DATA_DIR_ENV], "/old")
    read_env(DATA_DIR_ENV)
    read_env(DATA_DIR_ENV)
    read_env(DATA_DIR_ENV)
    err = capsys.readouterr().err
    assert err.count("Warning:") == 1
    assert "ABN_COMBINED_DATA_DIR" in err


def test_the_new_name_alone_writes_no_warning(monkeypatch, capsys) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, "/new")
    read_env(DATA_DIR_ENV)
    assert capsys.readouterr().err == ""


def test_neither_name_writes_no_warning(capsys) -> None:
    read_env(DATA_DIR_ENV)
    assert capsys.readouterr().err == ""


def test_both_names_still_write_the_warning(monkeypatch, capsys) -> None:
    """The old name is still in the profile, so the user must remove it."""
    monkeypatch.setenv(DATA_DIR_ENV, "/new")
    monkeypatch.setenv(LEGACY_ENV_NAMES[DATA_DIR_ENV], "/old")
    assert read_env(DATA_DIR_ENV) == "/new"
    assert "ABN_COMBINED_DATA_DIR" in capsys.readouterr().err


# --- each reader -----------------------------------------------------------


def test_the_data_directory_reads_each_name(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "new"))
    assert resolve_data_dir() == (tmp_path / "new").resolve()

    monkeypatch.delenv(DATA_DIR_ENV)
    monkeypatch.setenv(LEGACY_ENV_NAMES[DATA_DIR_ENV], str(tmp_path / "old"))
    assert resolve_data_dir() == (tmp_path / "old").resolve()


def test_the_option_wins_over_each_name(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "new"))
    monkeypatch.setenv(LEGACY_ENV_NAMES[DATA_DIR_ENV], str(tmp_path / "old"))
    assert resolve_data_dir(tmp_path / "given") == (tmp_path / "given").resolve()


def test_the_browser_reads_each_name(monkeypatch) -> None:
    from abn_combined.cli import _browser_is_wanted

    assert _browser_is_wanted(no_browser_flag=False) is True
    monkeypatch.setenv(LEGACY_ENV_NAMES[NO_BROWSER_ENV], "1")
    assert _browser_is_wanted(no_browser_flag=False) is False
    monkeypatch.delenv(LEGACY_ENV_NAMES[NO_BROWSER_ENV])
    monkeypatch.setenv(NO_BROWSER_ENV, "1")
    assert _browser_is_wanted(no_browser_flag=False) is False


def test_an_empty_value_stops_nothing(monkeypatch) -> None:
    from abn_combined.cli import _browser_is_wanted

    monkeypatch.setenv(NO_BROWSER_ENV, "")
    monkeypatch.setenv(LEGACY_ENV_NAMES[NO_BROWSER_ENV], "")
    assert _browser_is_wanted(no_browser_flag=False) is True


def test_the_logging_reads_each_name(monkeypatch) -> None:
    seen: list[str | None] = []
    monkeypatch.setattr(settings_mod, "read_env",
                        lambda name, default=None: seen.append(name) or default)
    from abn_combined import logging_config

    monkeypatch.setattr(logging_config, "read_env",
                        lambda name, default=None: "production" if name == LOG_ENV else default)
    logging_config.configure_logging()

    monkeypatch.setenv(LEGACY_ENV_NAMES[LOG_ENV], "production")
    monkeypatch.setattr(logging_config, "read_env", read_env)
    assert read_env(LOG_ENV, "development") == "production"


def test_the_settings_still_build(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path))
    assert Settings.create().data_dir == tmp_path.resolve()
