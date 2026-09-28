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
def no_worker(monkeypatch):
    """Prevent the start endpoints from launching real download threads."""
    calls: list[tuple] = []

    def _fake_abn(registry, settings, accounts, from_date, to_date, cdp_url=None, *a, **kw):
        calls.append(("abn", from_date, to_date, cdp_url))

    def _fake_paypal(registry, settings, from_date, to_date, cdp_url, *a, **kw):
        calls.append(("paypal", from_date, to_date, cdp_url))

    def _fake_wise(registry, settings, from_date, to_date, cdp_url=None, *a, **kw):
        calls.append(("wise", from_date, to_date, cdp_url))

    def _fake_seb(registry, settings, cdp_url=None, *a, **kw):
        calls.append(("seb", None, None, cdp_url))

    import abn_combined.downloaders.abn as abn_mod
    import abn_combined.downloaders.paypal as pp_mod
    import abn_combined.downloaders.seb as seb_mod
    import abn_combined.downloaders.wise as wise_mod

    monkeypatch.setattr(abn_mod, "run_abn_job", _fake_abn)
    monkeypatch.setattr(pp_mod, "run_paypal_job", _fake_paypal)
    monkeypatch.setattr(wise_mod, "run_wise_job", _fake_wise)
    monkeypatch.setattr(seb_mod, "run_seb_job", _fake_seb)
    return calls


# ---------------------------------------------------------------------------
# Download page
# ---------------------------------------------------------------------------


def test_download_page_renders(client) -> None:
    resp = client.get("/download")
    assert resp.status_code == 200
    html = resp.text
    assert "ABN AMRO" in html
    assert "PayPal" in html
    assert "Start ABN download" in html
    assert "Start PayPal download" in html
    # One shared Chrome panel instead of per-source launch buttons.
    assert html.count("Launch Chrome") == 1
    assert 'id="cdp-url"' in html
    assert "Wise" in html
    assert "SEB" in html
    assert "Start Wise download" in html
    assert "Start SEB download" in html
    # Dates prefilled (YYYY-MM-DD for all dated sources)
    assert 'name="from_date"' in html
    # Chrome launch commands shown for all sources.
    assert "--remote-debugging-port=9226" in html


def test_download_page_prefills_dates_from_download_state(client, app) -> None:
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
    assert 'value="2026-06-21"' in resp.text


def test_download_page_dates_clamped_when_bookmark_is_today(client, app) -> None:
    """A bookmark ending today must prefill from == to == today, not tomorrow."""
    from datetime import date

    from abn_combined.core.models import DownloadState
    from abn_combined.db import get_session_factory

    today = date.today()
    with get_session_factory()() as db:
        for source in ("abn", "paypal", "wise"):
            db.add(DownloadState(source=source, account=None, last_range_end=today))
        db.commit()

    resp = client.get("/download")
    assert resp.status_code == 200
    assert today.strftime("%Y-%m-%d") in resp.text
    # Tomorrow must not appear as a prefilled from-date anywhere.
    from datetime import timedelta

    tomorrow = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    assert f'value="{tomorrow}"' not in resp.text


def test_download_page_shows_running_job_status(client, fresh_registry) -> None:
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


def test_start_abn_download(client, no_worker, fresh_registry) -> None:
    import time

    resp = client.post(
        "/api/download/abn",
        data={"from_date": "2026-06-01", "to_date": "2026-06-30"},
    )
    assert resp.status_code == 200
    job = fresh_registry.get("abn")
    assert job is not None
    # Status partial returned.
    assert "download-status" in resp.text
    # The form's YYYY-MM-DD dates reach the worker as DD-MM-YYYY (ABN API format).
    for _ in range(50):
        if no_worker:
            break
        time.sleep(0.02)
    assert no_worker and no_worker[0][1:3] == ("01-06-2026", "30-06-2026")


def test_start_abn_download_rejects_bad_date(client, no_worker, fresh_registry) -> None:
    resp = client.post(
        "/api/download/abn",
        data={"from_date": "01-06-2026", "to_date": "2026-06-30"},
    )
    assert resp.status_code == 400
    assert "YYYY-MM-DD" in resp.json()["detail"]


def test_start_abn_download_conflict_while_running(client, no_worker, fresh_registry) -> None:
    fresh_registry.create("abn")  # pending = running
    resp = client.post("/api/download/abn", data={})
    assert resp.status_code == 409


def test_start_abn_download_allowed_after_terminal(client, no_worker, fresh_registry) -> None:
    fresh_registry.create("abn")
    fresh_registry.update_state("abn", JobState.FAILED, "old failure")
    resp = client.post("/api/download/abn", data={})
    assert resp.status_code == 200


def test_start_abn_passes_custom_cdp_url(client, no_worker) -> None:
    import time

    resp = client.post(
        "/api/download/abn",
        data={
            "from_date": "2026-06-01",
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


def test_download_page_uses_matching_cdp_default(client) -> None:
    """The CDP URL input's default must match `DEFAULT_CDP_URL` (9226) —
    previously hardcoded to 9222, a stale value that silently disagreed with
    the actual default the backend/launch command use."""
    from abn_combined.downloaders.browser import DEFAULT_CDP_URL

    resp = client.get("/download")
    assert DEFAULT_CDP_URL in resp.text
    assert "9222" not in resp.text


def test_launch_chrome_button(client, monkeypatch) -> None:
    # The route does a call-time `from ..downloaders.browser import
    # launch_chrome_debug` (matching this module's existing convention of
    # local-importing downloader functions, e.g. `run_paypal_job` above) —
    # patch the source module, not `abn_combined.api.downloads`.
    import abn_combined.downloaders.browser as browser_mod

    calls: list[tuple] = []
    monkeypatch.setattr(
        browser_mod,
        "launch_chrome_debug",
        lambda cdp_url, start_url="": calls.append((cdp_url, start_url)),
    )

    resp = client.post(
        "/api/download/launch-chrome", data={"cdp_url": "http://127.0.0.1:9226"}
    )
    assert resp.status_code == 200
    assert "Chrome launching" in resp.text
    assert calls == [("http://127.0.0.1:9226", "")]


def test_launch_chrome_button_missing_chrome(client, monkeypatch) -> None:
    import abn_combined.downloaders.browser as browser_mod

    def _raise(cdp_url, start_url=""):
        raise FileNotFoundError("Chrome not found at '/Applications/Google Chrome.app/...'")

    monkeypatch.setattr(browser_mod, "launch_chrome_debug", _raise)

    resp = client.post("/api/download/launch-chrome", data={})
    assert resp.status_code == 200
    assert "Chrome not found" in resp.text
    assert "alert-danger" in resp.text


# ---------------------------------------------------------------------------
# Wise / SEB start endpoints
# ---------------------------------------------------------------------------


def test_start_wise_download_passes_dates_and_cdp_url(client, no_worker, fresh_registry) -> None:
    import time

    resp = client.post(
        "/api/download/wise",
        data={
            "from_date": "2026-06-01",
            "to_date": "2026-06-30",
            "cdp_url": "http://127.0.0.1:9333",
        },
    )
    assert resp.status_code == 200
    assert fresh_registry.get("wise") is not None
    for _ in range(50):
        if no_worker:
            break
        time.sleep(0.02)
    assert no_worker and no_worker[0] == ("wise", "2026-06-01", "2026-06-30", "http://127.0.0.1:9333")


def test_start_wise_download_conflict_while_running(client, no_worker, fresh_registry) -> None:
    fresh_registry.create("wise")
    resp = client.post("/api/download/wise", data={})
    assert resp.status_code == 409


def test_start_seb_download(client, no_worker, fresh_registry) -> None:
    import time

    resp = client.post("/api/download/seb", data={"cdp_url": "http://127.0.0.1:9333"})
    assert resp.status_code == 200
    assert fresh_registry.get("seb") is not None
    assert "download-status" in resp.text
    for _ in range(50):
        if no_worker:
            break
        time.sleep(0.02)
    assert no_worker and no_worker[0] == ("seb", None, None, "http://127.0.0.1:9333")


def test_start_seb_download_conflict_while_running(client, no_worker, fresh_registry) -> None:
    fresh_registry.create("seb")
    resp = client.post("/api/download/seb", data={})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Status polling
# ---------------------------------------------------------------------------


def test_status_unknown_source_404(client) -> None:
    resp = client.get("/api/download/bogus/status")
    assert resp.status_code == 404


def test_status_terminal_job_reenables_submit_button_oob(client, fresh_registry) -> None:
    """When the job ends, the polled partial must swap the card's submit
    button back to its enabled state out-of-band — otherwise the button
    stays stuck on 'Running…' until a full page reload."""
    fresh_registry.create("paypal")
    fresh_registry.update_state("paypal", JobState.DONE, "Done — 0 new")
    resp = client.get("/api/download/paypal/status")
    html = resp.text
    assert 'id="paypal-submit" hx-swap-oob="true"' in html
    assert "Start PayPal download" in html
    assert "Running…" not in html


def test_status_running_job_disables_submit_button_oob(client, fresh_registry) -> None:
    fresh_registry.create("abn")
    fresh_registry.update_state("abn", JobState.DOWNLOADING, "Downloading…")
    resp = client.get("/api/download/abn/status")
    html = resp.text
    assert 'id="abn-submit" hx-swap-oob="true"' in html
    assert "Running…" in html


def test_download_page_render_has_no_oob_attrs(client, fresh_registry) -> None:
    """Full-page render must not emit hx-swap-oob (it would duplicate ids)."""
    fresh_registry.create("abn")
    fresh_registry.update_state("abn", JobState.DONE, "Done")
    resp = client.get("/download")
    assert "hx-swap-oob" not in resp.text


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
