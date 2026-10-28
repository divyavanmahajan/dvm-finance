"""Application settings and data-directory resolution."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "abn-combined"
DEFAULT_CURRENCY = "EUR"

# Each environment variable carries the prefix of the package and of the
# command. The project used the name `abn-combined` before, so the application
# still reads the old name of each variable. A later major version removes the
# old names, and this table is then the one place that changes.
DATA_DIR_ENV = "DVM_FINANCE_DATA_DIR"
NO_BROWSER_ENV = "DVM_FINANCE_NO_BROWSER"
LOG_ENV = "DVM_FINANCE_LOG_ENV"

LEGACY_ENV_NAMES = {
    DATA_DIR_ENV: "ABN_COMBINED_DATA_DIR",
    NO_BROWSER_ENV: "ABN_COMBINED_NO_BROWSER",
    LOG_ENV: "ABN_COMBINED_LOG_ENV",
}

# The application warns one time for each old name it reads.
_WARNED: set[str] = set()


def read_env(name: str, default: str | None = None) -> str | None:
    """Read an environment variable, and accept the old name of it.

    The new name wins when both names hold a value. The function writes one
    warning for each old name from which it reads a value. The warning goes to
    the standard error stream, because the command resolves the data directory
    before it configures the logging.
    """
    value = os.getenv(name)
    if value:
        _warn_once_about_legacy(name)
        return value

    legacy_name = LEGACY_ENV_NAMES.get(name)
    if legacy_name:
        legacy_value = os.getenv(legacy_name)
        if legacy_value:
            _warn_once_about_legacy(name)
            return legacy_value
    return default


def _warn_once_about_legacy(name: str) -> None:
    """Warn one time when the environment still holds the old name."""
    legacy_name = LEGACY_ENV_NAMES.get(name)
    if not legacy_name or not os.getenv(legacy_name):
        return
    if legacy_name in _WARNED:
        return
    _WARNED.add(legacy_name)
    print(
        f"Warning: the environment variable {legacy_name} has the old name. "
        f"Use {name} instead. A later major version reads the old name no more.",
        file=sys.stderr,
    )


def resolve_data_dir(data_dir: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the data directory.

    Precedence: explicit ``data_dir`` arg > ``DVM_FINANCE_DATA_DIR`` env var >
    platform user-data dir. The old name of the variable still works.
    """
    if data_dir:
        return Path(data_dir).expanduser().resolve()
    env_value = read_env(DATA_DIR_ENV)
    if env_value:
        return Path(env_value).expanduser().resolve()
    return Path(user_data_dir(APP_NAME)).resolve()


@dataclass
class Settings:
    """Runtime configuration for a single app instance."""

    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8000

    @classmethod
    def create(
        cls,
        data_dir: str | os.PathLike[str] | None = None,
        host: str = "127.0.0.1",
        port: int = 8000,
    ) -> Settings:
        return cls(data_dir=resolve_data_dir(data_dir), host=host, port=port)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "abn_combined.db"

    @property
    def browser_url(self) -> str:
        """Return the address that a browser can open.

        The host `0.0.0.0` means each interface. It is not an address that a
        browser can open, so the property gives the loopback address for it.
        """
        host = "127.0.0.1" if self.host == "0.0.0.0" else self.host  # noqa: S104
        return f"http://{host}:{self.port}"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def statements_dir(self) -> Path:
        return self.data_dir / "statements"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    def ensure_data_dir(self) -> None:
        """Create the data dir (and subdirs); raise a clear error if not writable."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.statements_dir.mkdir(parents=True, exist_ok=True)
            self.snapshots_dir.mkdir(parents=True, exist_ok=True)
            probe = self.data_dir / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise RuntimeError(
                f"Data directory is not writable: {self.data_dir} ({exc}). "
                f"Pass --data-dir or set {DATA_DIR_ENV} to a writable location."
            ) from exc
