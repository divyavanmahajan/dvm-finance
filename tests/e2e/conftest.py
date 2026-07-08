"""E2E harness (spec Testing §3): boot the app on a random port against a seeded
temp data dir and drive it with pytest-playwright (headless).

All tests here are marked ``e2e`` and excluded from the default run; execute with
``pytest -m e2e``. The ``live_app`` fixture starts a real uvicorn subprocess so the
browser talks to the app exactly as a user would (Alembic migrations, htmx swaps,
URL-encoded filter state included).
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from abn_combined.core.models import CategorizationRule, Transaction

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[2]
SCREENSHOT_DIR = REPO_ROOT / "docs" / "phase" / "init" / "13-e2e-and-release" / "screenshots"

# Runs a single app instance bound to a temp data dir; Alembic migrates on startup.
_RUNNER = """
import sys
import uvicorn
from abn_combined.app import create_app
from abn_combined.settings import Settings

settings = Settings.create(data_dir=sys.argv[1], port=int(sys.argv[2]))
uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.port, log_level="warning")
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(data_dir: Path, port: int) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-c", _RUNNER, str(data_dir), str(port)],
        cwd=str(REPO_ROOT),
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return proc
        except OSError:
            if proc.poll() is not None:
                raise RuntimeError("app process exited early") from None
            time.sleep(0.2)
    proc.terminate()
    raise RuntimeError("app did not start in time")


@dataclass
class LiveApp:
    """A running app instance plus helpers to read/seed its database."""

    base_url: str
    data_dir: Path

    def session(self) -> Session:
        engine = create_engine(f"sqlite:///{self.data_dir / 'abn_combined.db'}")
        return sessionmaker(bind=engine)()

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"


@pytest.fixture
def live_app(tmp_path):
    """Start the app on a random port against a fresh temp data dir."""
    data_dir = tmp_path / "data"
    port = _free_port()
    proc = _start_server(data_dir, port)
    try:
        yield LiveApp(base_url=f"http://127.0.0.1:{port}", data_dir=data_dir)
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def seed_transaction(
    db: Session,
    *,
    id: str,
    description: str,
    amount: float,
    txn_date: date,
    account: str = "NL01TEST0123456789",
    category: str | None = None,
    tags: str | None = None,
    manual_category: str | None = None,
    currency: str = "EUR",
    categorization_source: str | None = None,
) -> Transaction:
    txn = Transaction(
        id=id,
        accountNumber=account,
        transactiondate=txn_date,
        amount=amount,
        description=description,
        category=category,
        tags=tags,
        manual_category=manual_category,
        categorization_source=categorization_source,
        currency=currency,
    )
    db.add(txn)
    return txn


def seed_rule(
    db: Session,
    *,
    match_value: str,
    category: str,
    rule_type: str = "keyword",
    match_pattern: str = "contains",
    field_target: str = "description",
    priority: int = 100,
    tags: str | None = None,
) -> CategorizationRule:
    rule = CategorizationRule(
        rule_type=rule_type,
        match_pattern=match_pattern,
        field_target=field_target,
        match_value=match_value,
        category=category,
        tags=tags,
        priority=priority,
        is_active=True,
    )
    db.add(rule)
    return rule
