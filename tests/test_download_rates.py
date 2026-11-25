"""The SEB and First Tech download jobs without the ECB rates (no real Chrome).

A fake Playwright gives each job a statement file. The rate fetch gives no
rates, so the import refuses the file. The job must show the parse error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import abn_combined.parsers.ftfcu as ftfcu_parser
import abn_combined.parsers.seb as seb_parser
from abn_combined.core.jobs import JobRegistry, JobState
from abn_combined.core.models import Transaction
from abn_combined.db import get_session_factory
from abn_combined.downloaders import ftfcu, seb

FIXTURES = Path(__file__).parent / "fixtures"


class _Resp:
    def __init__(self, body: bytes = b"", data: dict | None = None,
                 content_type: str = "application/json") -> None:
        self.ok = True
        self.status = 200
        self.headers = {"content-type": content_type}
        self._body = body
        self._data = data

    def json(self):
        return self._data

    def body(self):
        return self._body

    def text(self):
        return self._body.decode()


class _Request:
    def __init__(self, get_resp=None, post_resp=None) -> None:
        self._get, self._post = get_resp, post_resp

    def get(self, *a, **kw):
        return self._get

    def post(self, *a, **kw):
        return self._post


class _Page:
    def __init__(self, url="", request=None, form=None) -> None:
        self.url = url
        self.request = request
        self._form = form

    def goto(self, *a, **kw):
        pass

    def wait_for_selector(self, *a, **kw):
        pass

    def evaluate(self, *a, **kw):
        return self._form

    def close(self):
        pass


class _Context:
    def __init__(self, page: _Page, request=None) -> None:
        self.pages = [page]
        self.request = request
        self._page = page

    def new_page(self):
        return self._page


class _Browser:
    def __init__(self, context: _Context) -> None:
        self.contexts = [context]

    def close(self):
        pass


def _fake_playwright(monkeypatch, browser: _Browser) -> None:
    class _Chromium:
        def connect_over_cdp(self, url):
            return browser

    class _PW:
        chromium = _Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import playwright.sync_api

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: _PW())


@pytest.fixture
def no_rates(monkeypatch):
    monkeypatch.setattr(seb_parser, "_build_rate_cache", lambda dates: {})
    monkeypatch.setattr(ftfcu_parser, "build_rate_cache", lambda dates, currency: {})


def _count_rows() -> int:
    with get_session_factory()() as db:
        return db.query(Transaction).count()


def test_seb_job_without_rates_shows_the_parse_error(app, settings, monkeypatch, no_rates):
    accounts = {"data": {"active_accounts": [{"id": "a1", "bban": "50110466225"}]}}
    request = _Request(
        get_resp=_Resp(data=accounts),
        post_resp=_Resp(body=(FIXTURES / "seb_sample.csv").read_bytes()),
    )
    _fake_playwright(monkeypatch, _Browser(_Context(_Page(request=request))))

    reg = JobRegistry()
    reg.create("seb")
    seb.run_seb_job(reg, settings)
    job = reg.get("seb")

    assert job.state == JobState.FAILED
    assert "ECB exchange rates are not available" in job.message
    assert "Try again later" in job.message
    assert _count_rows() == 0


def test_ftfcu_job_without_rates_shows_the_parse_error(app, settings, monkeypatch, no_rates):
    accounts_url = "https://banking.firsttechfed.com/DashboardV2"
    monkeypatch.setattr(ftfcu, "is_accounts_url", lambda url: True)
    monkeypatch.setattr(ftfcu, "identify_cdp_endpoint", lambda url: "Chrome/157")
    monkeypatch.setattr(
        ftfcu, "list_page_targets", lambda url: [{"type": "page", "url": accounts_url}]
    )
    monkeypatch.setattr(ftfcu, "_has_accounts_tab", lambda targets: True)
    ofx = (FIXTURES / "ftfcu_sample.ofx").read_bytes()
    page = _Page(url=accounts_url, form={"token": "t", "accounts": [{"guid": "g1"}]})
    context = _Context(page, request=_Request(post_resp=_Resp(body=ofx, content_type="application/x-ofx")))
    _fake_playwright(monkeypatch, _Browser(context))

    reg = JobRegistry()
    reg.create("ftfcu")
    ftfcu.run_ftfcu_job(reg, settings, "2026-10-01", "2026-11-16")
    job = reg.get("ftfcu")

    assert job.state == JobState.FAILED
    assert "ECB exchange rates are not available" in job.message
    assert _count_rows() == 0
