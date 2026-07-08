"""Route tests for the Download page and job/status endpoints."""

from __future__ import annotations

import pytest

import abn_combined.core.jobs as jobs_module
from abn_combined.core.jobs import JobRegistry, JobState


@pytest.fixture(autouse=True)
def fresh_registry(monkeypatch):
    """Isolate the module-level job registry per test."""
    reg = JobRegistry()
    monkeypatch.setattr(jobs_module, "_registry", reg)
    return reg


@pytest.fixture
def playwright_on(monkeypatch):
    import abn_combined.api.downloads as dl

    monkeypatch.setattr(dl, "_playwright_available", lambda: True)


@pytest.fixture
def playwright_off(monkeypatch):
    import abn_combined.api.downloads as dl

    monkeypatch.setattr(dl, "_playwright_available", lambda: False)


@pytest.fixture
def no_worker(monkeypatch):
    """Prevent the start endpoints from launching real download threads."""
    calls: list[tuple] = []

    def _fake_abn(registry, settings, accounts, from_date, to_date, *a, **kw):
        calls.append(("abn", from_date, to_date))

    def _fake_paypal(registry, settings, from_date, to_date, cdp_url, *a, **kw):
        calls.append(("paypal", from_date, to_date, cdp_url))

    import abn_combined.downloaders.abn as abn_mod
    import abn_combined.downloaders.paypal as pp_mod

    monkeypatch.setattr(abn_mod, "run_abn_job", _fake_abn)
    monkeypatch.setattr(pp_mod, "run_paypal_job", _fake_paypal)
    return calls


# ---------------------------------------------------------------------------
# Download page
# ---------------------------------------------------------------------------


def test_download_page_renders_with_playwright(client, playwright_on) -> None:
    resp = client.get("/download")
    assert resp.status_code == 200
    html = resp.text
    assert "ABN AMRO" in html
    assert "PayPal" in html
    assert "Start ABN download" in html
    assert "Start PayPal download" in html
    # Dates prefilled (DD-MM-YYYY for ABN, YYYY-MM-DD for PayPal patterns present)
    assert 'name="from_date"' in html
    # PayPal Chrome launch command shown
    assert "--remote-debugging-port=9222" in html


def test_download_page_without_playwright_shows_install_instructions(
    client, playwright_off
) -> None:
    resp = client.get("/download")
    assert resp.status_code == 200
    html = resp.text
    assert "playwright install chromium" in html
    assert "Start ABN download" not in html
    # PayPal card is still available (CDP uses the user's own Chrome).
    assert "Start PayPal download" in html


def test_download_page_prefills_dates_from_download_state(
    client, app, playwright_on
) -> None:
    """After a successful download, the ABN from-date defaults to the day after."""
    from datetime import date

    from abn_combined.core.models import DownloadState
    from abn_combined.db import get_session_factory

    with get_session_factory()() as db:
        db.add(
            DownloadState(
                source="abn",
                account=None,
                last_range_end=date(2026, 6, 20),
            )
        )
        db.commit()

    resp = client.get("/download")
    assert resp.status_code == 200
    assert 'value="21-06-2026"' in resp.text


def test_download_page_shows_running_job_status(
    client, playwright_on, fresh_registry
) -> None:
    """A running job renders its status (with polling) on the page itself."""
    fresh_registry.create("abn")
    fresh_registry.update_state("abn", JobState.DOWNLOADING, "Downloading MT940 files…")
    resp = client.get("/download")
    html = resp.text
    assert "download-status" in html
    assert 'hx-trigger="every 2s"' in html
    assert "/api/download/abn/status" in html
    # Start button disabled while running.
    assert "Running…" in html


# ---------------------------------------------------------------------------
# Start endpoints
# ---------------------------------------------------------------------------


def test_start_abn_download(client, playwright_on, no_worker, fresh_registry) -> None:
    resp = client.post(
        "/api/download/abn",
        data={"from_date": "01-06-2026", "to_date": "30-06-2026"},
    )
    assert resp.status_code == 200
    job = fresh_registry.get("abn")
    assert job is not None
    # Status partial returned.
    assert "download-status" in resp.text


def test_start_abn_download_conflict_while_running(
    client, playwright_on, no_worker, fresh_registry
) -> None:
    fresh_registry.create("abn")  # pending = running
    resp = client.post("/api/download/abn", data={})
    assert resp.status_code == 409


def test_start_abn_download_allowed_after_terminal(
    client, playwright_on, no_worker, fresh_registry
) -> None:
    fresh_registry.create("abn")
    fresh_registry.update_state("abn", JobState.FAILED, "old failure")
    resp = client.post("/api/download/abn", data={})
    assert resp.status_code == 200


def test_start_abn_download_503_without_playwright(
    client, playwright_off, no_worker
) -> None:
    resp = client.post("/api/download/abn", data={})
    assert resp.status_code == 503
    assert "playwright install chromium" in resp.json()["detail"]


def test_start_paypal_download(client, no_worker, fresh_registry) -> None:
    resp = client.post(
        "/api/download/paypal",
        data={"from_date": "2026-01-01", "to_date": "2026-06-30"},
    )
    assert resp.status_code == 200
    assert fresh_registry.get("paypal") is not None


def test_start_paypal_download_conflict_while_running(
    client, no_worker, fresh_registry
) -> None:
    fresh_registry.create("paypal")
    resp = client.post("/api/download/paypal", data={})
    assert resp.status_code == 409


def test_start_paypal_passes_custom_cdp_url(client, no_worker) -> None:
    import time

    resp = client.post(
        "/api/download/paypal",
        data={
            "from_date": "2026-01-01",
            "to_date": "2026-06-30",
            "cdp_url": "http://127.0.0.1:9333",
        },
    )
    assert resp.status_code == 200
    # Worker runs in a thread; give it a moment.
    for _ in range(50):
        if no_worker:
            break
        time.sleep(0.02)
    assert no_worker and no_worker[0][3] == "http://127.0.0.1:9333"


# ---------------------------------------------------------------------------
# Status polling
# ---------------------------------------------------------------------------


def test_status_unknown_source_404(client) -> None:
    resp = client.get("/api/download/bogus/status")
    assert resp.status_code == 404


def test_status_no_job_returns_empty(client) -> None:
    resp = client.get("/api/download/abn/status")
    assert resp.status_code == 200
    assert "download-status" not in resp.text


def test_status_running_job_has_polling_attrs(client, fresh_registry) -> None:
    fresh_registry.create("abn")
    fresh_registry.update_state("abn", JobState.DOWNLOADING, "Downloading MT940 files…")
    resp = client.get("/api/download/abn/status")
    assert resp.status_code == 200
    html = resp.text
    assert "downloading" in html
    assert 'hx-trigger="every 2s"' in html
    assert "/api/download/abn/status" in html


def test_status_terminal_job_stops_polling(client, fresh_registry) -> None:
    fresh_registry.create("abn")
    fresh_registry.update_state("abn", JobState.DONE, "Done")
    resp = client.get("/api/download/abn/status")
    html = resp.text
    assert "hx-trigger" not in html
    assert "done" in html


def test_status_failed_job_shows_message(client, fresh_registry) -> None:
    fresh_registry.create("paypal")
    fresh_registry.update_state(
        "paypal", JobState.FAILED, "Could not connect to Chrome at http://127.0.0.1:9222"
    )
    resp = client.get("/api/download/paypal/status")
    html = resp.text
    assert "failed" in html
    assert "Could not connect to Chrome" in html
    assert "hx-trigger" not in html


def test_status_done_job_shows_summary_with_transactions_link(
    client, fresh_registry
) -> None:
    fresh_registry.create("abn")
    fresh_registry.set_summary(
        "abn",
        {
            "files": ["MT940260630.STA"],
            "new": 12,
            "duplicates": 3,
            "categorized": 10,
            "uncategorized": 2,
            "failed_files": [],
        },
    )
    fresh_registry.update_state("abn", JobState.DONE, "Done — 12 new")
    resp = client.get("/api/download/abn/status")
    html = resp.text
    assert "/transactions?source_file=MT940260630.STA" in html
    assert "12" in html
