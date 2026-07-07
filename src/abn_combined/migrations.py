"""Alembic migration runner (invoked on app startup)."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command

from .logging_config import get_logger
from .settings import Settings

logger = get_logger(__name__)

_PACKAGE_DIR = Path(__file__).parent
_ALEMBIC_INI = _PACKAGE_DIR.parent.parent / "alembic.ini"
_ALEMBIC_DIR = _PACKAGE_DIR.parent.parent / "alembic"


def _alembic_config(settings: Settings) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def upgrade_to_head(settings: Settings) -> None:
    """Run ``alembic upgrade head`` against the data-dir database.

    Falls back to ``metadata.create_all`` if the alembic environment is not yet
    present (e.g. during early incremental builds).
    """
    if _ALEMBIC_INI.exists() and _ALEMBIC_DIR.exists():
        command.upgrade(_alembic_config(settings), "head")
        logger.info("alembic_upgraded", url=settings.database_url)
    else:  # pragma: no cover - only during step-01 scaffolding
        from .db import get_engine

        try:
            from .core.models import Base

            Base.metadata.create_all(get_engine())
            logger.info("schema_create_all_fallback")
        except ImportError:
            logger.info("no_migrations_available")
