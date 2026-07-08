"""Alembic migration runner (invoked on app startup)."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command

from .logging_config import get_logger
from .settings import Settings

logger = get_logger(__name__)

_PACKAGE_DIR = Path(__file__).parent
# Packaged installs (wheel / uvx): the alembic tree is bundled inside the package
# via hatchling force-include (see pyproject.toml).
_PKG_ALEMBIC_INI = _PACKAGE_DIR / "alembic.ini"
_PKG_ALEMBIC_DIR = _PACKAGE_DIR / "alembic"
# Editable install / source checkout: the alembic tree lives at the repo root.
_REPO_ALEMBIC_INI = _PACKAGE_DIR.parent.parent / "alembic.ini"
_REPO_ALEMBIC_DIR = _PACKAGE_DIR.parent.parent / "alembic"


def _resolve_alembic_paths() -> tuple[Path, Path] | None:
    """Locate the alembic.ini + migration tree (packaged wheel, then source)."""
    if _PKG_ALEMBIC_INI.exists() and _PKG_ALEMBIC_DIR.exists():
        return _PKG_ALEMBIC_INI, _PKG_ALEMBIC_DIR
    if _REPO_ALEMBIC_INI.exists() and _REPO_ALEMBIC_DIR.exists():
        return _REPO_ALEMBIC_INI, _REPO_ALEMBIC_DIR
    return None


def _alembic_config(settings: Settings) -> Config:
    """Build an Alembic Config pointing at the resolved migration tree.

    Raises RuntimeError if the alembic tree cannot be located.
    """
    paths = _resolve_alembic_paths()
    if paths is None:  # pragma: no cover - guarded by upgrade_to_head
        raise RuntimeError("Alembic migration tree not found")
    ini, script_dir = paths
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(script_dir))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def upgrade_to_head(settings: Settings) -> None:
    """Run ``alembic upgrade head`` against the data-dir database.

    Falls back to ``metadata.create_all`` only if the alembic tree is missing
    entirely (should not happen for packaged or source installs — the tree is
    bundled into the wheel).
    """
    if _resolve_alembic_paths() is not None:
        command.upgrade(_alembic_config(settings), "head")
        logger.info("alembic_upgraded", url=settings.database_url)
    else:  # pragma: no cover - only if the alembic tree is somehow absent
        from .db import get_engine

        try:
            from .core.models import Base

            Base.metadata.create_all(get_engine())
            logger.info("schema_create_all_fallback")
        except ImportError:
            logger.info("no_migrations_available")
