"""Unit tests for the First Tech Federal Credit Union downloader (no real Chrome)."""

from __future__ import annotations

from datetime import date

import pytest

from abn_combined.core.jobs import JobRegistry, JobState
from abn_combined.downloaders import ftfcu

TODAY = date(2026, 11, 16)


# --- clamp_range --------------------------------------------------------------


def test_clamp_range_keeps_a_valid_range():
    assert ftfcu.clamp_range("2026-10-01", "2026-11-16", TODAY) == ("2026-10-01", "2026-11-16")


def test_clamp_range_limits_start_to_two_years():
    assert ftfcu.clamp_range("2020-01-01", "2026-11-16", TODAY) == ("2024-11-16", "2026-11-16")


def test_clamp_range_limits_end_to_today():
    assert ftfcu.clamp_range("2026-11-01", "2026-12-31", TODAY) == ("2026-11-01", "2026-11-16")


def test_clamp_range_on_29_february():
    assert ftfcu.clamp_range("2000-01-01", "2028-02-29", date(2028, 2, 29))[0] == "2026-02-28"


@pytest.mark.parametrize(
    "start,end", [("01-10-2026", "2026-11-16"), ("2026-11-10", "2026-11-01"), ("", "2026-11-01")]
)
def test_clamp_range_rejects_bad_input(start, end):
    with pytest.raises(ValueError):
        ftfcu.clamp_range(start, end, TODAY)


# --- build_export_body ------------------------------------------------------------


def test_export_body_repeats_account_identifiers_in_ui_order():
    body = ftfcu.build_export_body(
        "TOKEN", ["guid-1", "guid-2"], "2026-10-01", "2026-11-16", "2026-11-16", "BND"
    ).decode()
    names = [
        part.split('name="', 1)[1].split('"', 1)[0]
        for part in body.split("--BND")
        if 'name="' in part
    ]
    assert names == [
        "__RequestVerificationToken",
        "Parameters.TransactionCategoryId",
        "Parameters.Debit",
        "Parameters.Description",
        "Parameters.MaximumAmount",
        "Parameters.MinimumAmount",
        "Parameters.TransactionTypeId",
        "Parameters.StartCheckNumber",
        "Parameters.EndCheckNumber",
        "format",
        "Parameters.StartDate",
        "Parameters.EndDate",
        "Parameters.TodaysDate",
        "AccountIdentifiers",
        "AccountIdentifiers",
    ]
    assert 'name="format"\r\n\r\n56\r\n' in body
    assert 'name="Parameters.MaximumAmount"\r\n\r\n-1\r\n' in body
    assert 'name="AccountIdentifiers"\r\n\r\nguid-2\r\n' in body
    assert body.endswith("--BND--\r\n")


def test_count_ofx_transactions():
    assert ftfcu.count_ofx_transactions(b"<STMTTRNRS><STMTTRN>a</STMTTRN><STMTTRN>b") == 2
    assert ftfcu.count_ofx_transactions(b"<STMTTRNRS><BANKTRANLIST></BANKTRANLIST>") == 0


def test_is_accounts_url():
    assert ftfcu.is_accounts_url("https://banking.firsttechfed.com/MyAccountsV2")
    assert ftfcu.is_accounts_url("https://banking.firsttechfed.com/myaccountsv2?x=1")
    assert not ftfcu.is_accounts_url(
        "https://banking.firsttechfed.com/Authentication?ReturnUrl=MyAccountsV2"
    )


# --- run_ftfcu_job ---------------------------------------------------------------


def _run(settings, **kw):
    reg = JobRegistry()
    reg.create("ftfcu")
    ftfcu.run_ftfcu_job(reg, settings, kw.pop("from_date", "2026-10-01"),
                        kw.pop("to_date", "2026-11-16"), **kw)
    return reg.get("ftfcu")


def test_run_job_invalid_dates_fail(settings):
    job = _run(settings, from_date="01-10-2026")
    assert job.state == JobState.FAILED
    assert "Invalid date" in job.message


def test_run_job_cdp_unreachable_fails_with_launch_command(settings):
    job = _run(settings, cdp_url="http://127.0.0.1:59999")
    assert job.state == JobState.FAILED
    assert "--remote-debugging-port=59999" in job.message
    assert "Could not connect to Chrome" in job.message


def test_run_job_opens_tab_without_attach_and_times_out(settings, monkeypatch):
    """No First Tech tab → open one over HTTP; never attach before the login."""
    opened: list[str] = []
    monkeypatch.setattr(ftfcu, "identify_cdp_endpoint", lambda url: "Chrome/157")
    monkeypatch.setattr(
        ftfcu,
        "list_page_targets",
        lambda url: [{"type": "page", "url": "https://banking.firsttechfed.com/Authentication"}]
        if opened
        else [{"type": "page", "url": "https://example.com/"}],
    )
    monkeypatch.setattr(ftfcu, "open_tab", lambda cdp, url: opened.append(url))
    monkeypatch.setattr(ftfcu, "_AUTH_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(ftfcu, "_AUTH_POLL_SECONDS", 0)

    def _no_attach(*a, **kw):  # pragma: no cover - must not run
        raise AssertionError("the job attached before the login")

    import playwright.sync_api

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", _no_attach)

    job = _run(settings)
    assert opened == [ftfcu.FTFCU_ACCOUNTS_URL]
    assert job.state == JobState.FAILED
    assert "Login timeout" in job.message


def test_blob_tab_is_not_a_first_tech_tab(settings, monkeypatch):
    """A leftover blob: download tab must not stop the job from opening a real tab."""
    assert not ftfcu.is_ftfcu_url("blob:https://banking.firsttechfed.com/5d710d6f")
    assert not ftfcu.is_accounts_url("blob:https://banking.firsttechfed.com/MyAccountsV2")
    opened: list[str] = []
    monkeypatch.setattr(ftfcu, "identify_cdp_endpoint", lambda url: "Chrome/157")
    monkeypatch.setattr(
        ftfcu,
        "list_page_targets",
        lambda url: [{"type": "page", "url": "blob:https://banking.firsttechfed.com/5d710d6f"}],
    )
    monkeypatch.setattr(ftfcu, "open_tab", lambda cdp, url: opened.append(url))
    monkeypatch.setattr(ftfcu, "_AUTH_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(ftfcu, "_AUTH_POLL_SECONDS", 0)

    _run(settings)
    assert opened == [ftfcu.FTFCU_ACCOUNTS_URL]


def test_run_job_reuses_existing_tab(settings, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(ftfcu, "identify_cdp_endpoint", lambda url: "Chrome/157")
    monkeypatch.setattr(
        ftfcu,
        "list_page_targets",
        lambda url: [{"type": "page", "url": "https://banking.firsttechfed.com/Authentication"}],
    )
    monkeypatch.setattr(ftfcu, "open_tab", lambda cdp, url: opened.append(url))
    monkeypatch.setattr(ftfcu, "_AUTH_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(ftfcu, "_AUTH_POLL_SECONDS", 0)

    job = _run(settings)
    assert opened == []
    assert job.state == JobState.FAILED
