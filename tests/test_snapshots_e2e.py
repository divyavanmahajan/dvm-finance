"""Browser verification for snapshot sharing (marked e2e, excluded by default).

Boots two app instances on two temp data dirs ("machine A" and "machine B"),
exports a snapshot from A via the browser (real download), imports it into B via
the upload form, and verifies incoming-wins plus the rendered import report.
Screenshots land in docs/phase/init/11-snapshot-sharing/screenshots/.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from abn_combined.core.models import CategorizationRule, Transaction

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = REPO_ROOT / "docs" / "phase" / "init" / "11-snapshot-sharing" / "screenshots"

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


def _session(data_dir: Path):
    engine = create_engine(f"sqlite:///{data_dir / 'abn_combined.db'}")
    return sessionmaker(bind=engine)()


def _seed(data_dir: Path, manual_category: str) -> None:
    db = _session(data_dir)
    db.add(
        Transaction(
            id="txn-shared",
            accountNumber="NL01TEST0123456789",
            transactiondate=date(2026, 3, 1),
            amount=-25,
            description="Albert Heijn Amsterdam",
            manual_category=manual_category,
            categorization_source="manual",
            currency="EUR",
        )
    )
    db.commit()
    db.close()


def test_snapshot_sharing_between_two_machines(tmp_path, page):
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    dir_a, dir_b = tmp_path / "machine_a", tmp_path / "machine_b"
    port_a, port_b = _free_port(), _free_port()
    proc_a = _start_server(dir_a, port_a)
    proc_b = _start_server(dir_b, port_b)
    try:
        _seed(dir_a, manual_category="groceries")
        db_a = _session(dir_a)
        db_a.add(
            CategorizationRule(
                rule_type="keyword", match_pattern="contains",
                field_target="description", match_value="albert heijn",
                category="groceries",
            )
        )
        db_a.commit()
        db_a.close()
        _seed(dir_b, manual_category="dining")  # conflicting local edit on B

        # Uses the pytest-playwright `page` fixture (headless Chromium) so this test
        # coexists with the other e2e flows in one session.
        # Machine A: export via the button (a real browser download).
        page.goto(f"http://127.0.0.1:{port_a}/snapshots")
        with page.expect_download() as dl_info:
            page.click("form[action='/snapshots/export'] button")
        snapshot_file = tmp_path / dl_info.value.suggested_filename
        dl_info.value.save_as(snapshot_file)
        assert snapshot_file.stat().st_size > 0

        page.goto(f"http://127.0.0.1:{port_a}/snapshots")
        assert page.locator("table.snapshot-exports tbody tr").count() == 1
        page.screenshot(path=str(SCREENSHOT_DIR / "export-list.png"), full_page=True)

        # Machine B: import the file via the upload form.
        page.goto(f"http://127.0.0.1:{port_b}/snapshots")
        page.set_input_files("form.snapshot-import-form input[type=file]",
                             str(snapshot_file))
        page.click("form.snapshot-import-form button")
        page.wait_for_url("**/snapshots?imported=*")
        assert page.locator(".snapshot-report.just-imported").count() == 1
        page.screenshot(path=str(SCREENSHOT_DIR / "import-report.png"),
                        full_page=True)

        # Incoming won: B's manual category was overwritten by A's value.
        db_b = _session(dir_b)
        txn = db_b.get(Transaction, "txn-shared")
        assert txn.manual_category == "groceries"
        assert db_b.query(CategorizationRule).count() == 1
        db_b.close()
        assert list(dir_b.glob("*.backup-*.db"))
    finally:
        proc_a.terminate()
        proc_b.terminate()
        proc_a.wait(timeout=10)
        proc_b.wait(timeout=10)
