"""Application settings and data-directory resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "abn-combined"
DATA_DIR_ENV = "ABN_COMBINED_DATA_DIR"
DEFAULT_CURRENCY = "EUR"


def resolve_data_dir(data_dir: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the data directory.

    Precedence: explicit ``data_dir`` arg > ``ABN_COMBINED_DATA_DIR`` env var >
    platform user-data dir.
    """
    if data_dir:
        return Path(data_dir).expanduser().resolve()
    env_value = os.getenv(DATA_DIR_ENV)
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
