"""Tests for the in-process download job registry (core/jobs.py)."""

from __future__ import annotations

import threading
import time

from abn_combined.core.jobs import DownloadJob, JobRegistry, JobState

# ---------------------------------------------------------------------------
# JobState
# ---------------------------------------------------------------------------


def test_job_state_values() -> None:
    assert JobState.PENDING == "pending"
    assert JobState.WAITING_FOR_AUTH == "waiting-for-auth"
    assert JobState.DOWNLOADING == "downloading"
    assert JobState.IMPORTING == "importing"
    assert JobState.DONE == "done"
    assert JobState.FAILED == "failed"


# ---------------------------------------------------------------------------
# DownloadJob
# ---------------------------------------------------------------------------


def test_download_job_defaults() -> None:
    job = DownloadJob(source="abn")
    assert job.source == "abn"
    assert job.state == JobState.PENDING
    assert job.message == ""
    assert job.import_summary is None
    assert job.finished_at is None
    assert not job.is_terminal()


def test_download_job_terminal_states() -> None:
    job = DownloadJob(source="abn", state=JobState.DONE)
    assert job.is_terminal()

    job2 = DownloadJob(source="abn", state=JobState.FAILED)
    assert job2.is_terminal()


def test_download_job_non_terminal_states() -> None:
    for state in (
        JobState.PENDING,
        JobState.WAITING_FOR_AUTH,
        JobState.DOWNLOADING,
        JobState.IMPORTING,
    ):
        job = DownloadJob(source="abn", state=state)
        assert not job.is_terminal(), f"{state} should not be terminal"


def test_download_job_as_dict() -> None:
    job = DownloadJob(source="paypal", state=JobState.DONE, message="ok")
    d = job.as_dict()
    assert d["source"] == "paypal"
    assert d["state"] == "done"
    assert d["message"] == "ok"
    assert "started_at" in d
    assert d["finished_at"] is None


# ---------------------------------------------------------------------------
# JobRegistry — basic operations
# ---------------------------------------------------------------------------


def test_registry_get_unknown_source() -> None:
    reg = JobRegistry()
    assert reg.get("abn") is None


def test_registry_create_and_get() -> None:
    reg = JobRegistry()
    job = reg.create("abn")
    assert job.state == JobState.PENDING
    assert reg.get("abn") is job


def test_registry_is_running_when_pending() -> None:
    reg = JobRegistry()
    reg.create("abn")
    assert reg.is_running("abn")


def test_registry_is_running_false_when_done() -> None:
    reg = JobRegistry()
    reg.create("abn")
    reg.update_state("abn", JobState.DONE)
    assert not reg.is_running("abn")


def test_registry_is_running_false_when_failed() -> None:
    reg = JobRegistry()
    reg.create("abn")
    reg.update_state("abn", JobState.FAILED, "oops")
    assert not reg.is_running("abn")


def test_registry_is_running_false_when_no_job() -> None:
    reg = JobRegistry()
    assert not reg.is_running("paypal")


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


def test_update_state_transitions() -> None:
    reg = JobRegistry()
    reg.create("abn")

    for state in (
        JobState.WAITING_FOR_AUTH,
        JobState.DOWNLOADING,
        JobState.IMPORTING,
        JobState.DONE,
    ):
        reg.update_state("abn", state, "msg")
        assert reg.get("abn").state == state

    assert reg.get("abn").finished_at is not None


def test_update_state_sets_finished_at_on_done() -> None:
    reg = JobRegistry()
    reg.create("abn")
    reg.update_state("abn", JobState.DONE)
    job = reg.get("abn")
    assert job.finished_at is not None


def test_update_state_sets_finished_at_on_failed() -> None:
    reg = JobRegistry()
    reg.create("abn")
    reg.update_state("abn", JobState.FAILED, "boom")
    job = reg.get("abn")
    assert job.finished_at is not None
    assert job.message == "boom"


def test_update_state_no_finished_at_on_intermediate() -> None:
    reg = JobRegistry()
    reg.create("abn")
    reg.update_state("abn", JobState.DOWNLOADING)
    assert reg.get("abn").finished_at is None


def test_update_state_returns_none_for_unknown_source() -> None:
    reg = JobRegistry()
    result = reg.update_state("bogus", JobState.DONE)
    assert result is None


def test_set_summary() -> None:
    reg = JobRegistry()
    reg.create("abn")
    reg.set_summary("abn", {"new": 5, "duplicates": 1})
    assert reg.get("abn").import_summary == {"new": 5, "duplicates": 1}


def test_set_summary_noop_for_unknown_source() -> None:
    reg = JobRegistry()
    reg.set_summary("unknown", {"new": 5})  # must not raise


# ---------------------------------------------------------------------------
# One job per source (create replaces previous)
# ---------------------------------------------------------------------------


def test_create_replaces_existing_job() -> None:
    reg = JobRegistry()
    old_job = reg.create("abn")
    reg.update_state("abn", JobState.DONE)
    new_job = reg.create("abn")
    assert new_job is not old_job
    assert new_job.state == JobState.PENDING


def test_two_sources_are_independent() -> None:
    reg = JobRegistry()
    reg.create("abn")
    reg.create("paypal")
    reg.update_state("abn", JobState.FAILED, "abn failed")
    assert reg.get("paypal").state == JobState.PENDING
    assert reg.get("abn").state == JobState.FAILED


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


def test_concurrent_updates_are_safe() -> None:
    """Multiple threads updating different states must not corrupt the registry."""
    reg = JobRegistry()
    reg.create("abn")
    errors: list[Exception] = []

    def _worker(state: JobState) -> None:
        try:
            time.sleep(0.001)
            reg.update_state("abn", state, f"from-{state}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=_worker, args=(s,))
        for s in (
            JobState.WAITING_FOR_AUTH,
            JobState.DOWNLOADING,
            JobState.IMPORTING,
            JobState.DONE,
        )
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    # Final state is one of the four applied (race is fine; no corruption).
    assert reg.get("abn") is not None


# ---------------------------------------------------------------------------
# Failure paths without hangs
# ---------------------------------------------------------------------------


def test_failed_job_message_preserved() -> None:
    reg = JobRegistry()
    reg.create("abn")
    reg.update_state(
        "abn",
        JobState.FAILED,
        "Authentication timeout — browser closed.",
    )
    job = reg.get("abn")
    assert job.state == JobState.FAILED
    assert "timeout" in job.message.lower()
    assert job.is_terminal()


def test_auth_timeout_path() -> None:
    """Simulate the ABN auth-timeout failure path without running Playwright."""
    reg = JobRegistry()
    reg.create("abn")
    reg.update_state("abn", JobState.WAITING_FOR_AUTH, "Waiting for auth…")
    # Timeout fires → fail
    reg.update_state(
        "abn",
        JobState.FAILED,
        "Authentication timeout — browser closed. Please retry.",
    )
    job = reg.get("abn")
    assert job.is_terminal()
    assert job.state == JobState.FAILED


def test_cdp_unavailable_path() -> None:
    """Simulate the PayPal CDP-unavailable failure path."""
    reg = JobRegistry()
    reg.create("paypal")
    reg.update_state("paypal", JobState.WAITING_FOR_AUTH, "Connecting to Chrome…")
    cdp_err = (
        "Could not connect to Chrome at http://127.0.0.1:9222. "
        "Please start Chrome with:\n"
        "/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome "
        "--remote-debugging-port=9222 …\n\n"
        "Error: Connection refused"
    )
    reg.update_state("paypal", JobState.FAILED, cdp_err)
    job = reg.get("paypal")
    assert job.is_terminal()
    assert "9222" in job.message
    assert "Chrome" in job.message


def test_import_failure_path() -> None:
    """Simulate failure during the import phase."""
    reg = JobRegistry()
    reg.create("abn")
    reg.update_state("abn", JobState.IMPORTING, "Importing 1 file…")
    reg.update_state("abn", JobState.FAILED, "No transactions found in file.STA")
    assert reg.get("abn").is_terminal()
