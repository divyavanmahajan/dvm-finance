"""Engine/session management bound to the data-dir SQLite database."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .settings import Settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def configure_engine(settings: Settings) -> Engine:
    """Create (or recreate) the process-wide engine bound to the settings DB path."""
    global _engine, _SessionLocal
    _engine = create_engine(
        settings.database_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Engine not configured. Call configure_engine(settings) first.")
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        raise RuntimeError("Session factory not configured. Call configure_engine(settings) first.")
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a database session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
