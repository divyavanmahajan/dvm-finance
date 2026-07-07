"""Tests for the download step: ported abn-download mocked tests + route tests.

Protocol tests are ported from /Users/divya/projects/abn-download/tests/
(test_abn_download.py, test_paypal_download.py) against the refactored modules.
No real bank/PayPal traffic — everything below runs against mocks.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import Mock

import pytest

from abn_combined.core.jobs import JobRegistry, JobState
from abn_combined.downloaders import abn, paypal

# ===========================================================================
# ABN — ported protocol tests
# ===========================================================================


def test_abn_transactions_url_constant() -> None:
    assert (
        abn.ABN_TRANSACTIONS_URL
        == "https://www.abnamro.nl/my-abnamro/payments/download-overviews/#/transactions"
    )


def test_abn_generations_api_constant() -> None:
    assert abn.ABN_GENERATIONS_API == "https://www.abnamro.nl/mutationreporting/generations/v1"


def test_download_transactions_payload_structure() -> None:
    """Ported: payload structure of the generations POST."""
    mock_page = Mock()
    mock_response = Mock()
    mock_response.ok = True
    mock_response.status = 200
    mock_response.json.return_value = {"reports": []}
    mock_page.request.post.return_value = mock_response

    account_numbers = ["123456789", "987654321"]
    abn.download_transactions(
        mock_page, account_numbers, "01-01-2025", "31-01-2025", from_last_download_date=False
    )

    mock_page.request.post.assert_called_once()
    call_args = mock_page.request.post.call_args
    assert call_args[0][0] == abn.ABN_GENERATIONS_API

    payload = call_args[1]["data"]
    assert "generations" in payload
    assert payload["generations"]["accountNumbers"] == account_numbers
    assert payload["generations"]["fromDate"] == "01-01-2025"
    assert payload["generations"]["toDate"] == "31-01-2025"
    assert payload["generations"]["fromLastDownloadDate"] is False
    assert payload["generations"]["format"] == "MT940"


def test_download_transactions_with_from_last_download() -> None:
    mock_page = Mock()
    mock_response = Mock()
    mock_response.ok = True
    mock_response.status = 200
    mock_response.json.return_value = {"reports": []}
    mock_page.request.post.return_value = mock_response

    abn.download_transactions(
        mock_page, ["123456789"], "01-01-2025", "31-01-2025", from_last_download_date=True
    )

    payload = mock_page.request.post.call_args[1]["data"]
    assert payload["generations"]["fromLastDownloadDate"] is True


def test_download_transactions_error_handling() -> None:
    mock_page = Mock()
    mock_response = Mock()
    mock_response.ok = False
    mock_response.status = 400
    mock_response.text.return_value = "Bad Request"
    mock_page.request.post.return_value = mock_response

    with pytest.raises(Exception, match="status 400"):
        abn.download_transactions(mock_page, ["123456789"], "01-01-2025", "31-01-2025")


def test_dismiss_cookie_banner_clicks_button() -> None:
    page = Mock()
    button = Mock()
    page.get_by_role.return_value = button

    abn.dismiss_cookie_banner(page)

    page.get_by_role.assert_called_once_with("button", name="I do not accept")
    button.click.assert_called_once()


def test_dismiss_cookie_banner_swallows_absence() -> None:
    page = Mock()
    page.get_by_role.side_effect = Exception("not found")
    abn.dismiss_cookie_banner(page)  # must not raise


# ---------------------------------------------------------------------------
# MT940 base64 decode + save
# ---------------------------------------------------------------------------


def test_decode_and_save_reports(tmp_path) -> None:
    content = b":940:\n:20:ABC\n"
    response_data = {
        "reports": [
            {"fileName": "MT940250101.STA", "fileBytes": base64.b64encode(content).decode()},
        ]
    }
    saved = abn.decode_and_save_reports(response_data, tmp_path)
    assert len(saved) == 1
    assert saved[0].name == "MT940250101.STA"
    assert saved[0].read_bytes() == content


def test_decode_and_save_reports_skips_missing_fields(tmp_path) -> None:
    response_data = {
        "reports": [
            {"fileName": "MT940.STA"},  # no fileBytes
            {"fileBytes": base64.b64encode(b"x").decode()},  # no fileName
        ]
    }
    saved = abn.decode_and_save_reports(response_data, tmp_path)
    assert saved == []


def test_decode_and_save_reports_empty_response(tmp_path) -> None:
    assert abn.decode_and_save_reports({}, tmp_path) == []
    assert abn.decode_and_save_reports({"reports": []}, tmp_path) == []


def test_decode_and_save_reports_multiple_files(tmp_path) -> None:
    response_data = {
        "reports": [
            {"fileName": f"MT940_{i}.STA", "fileBytes": base64.b64encode(f"file{i}".encode()).decode()}
            for i in range(3)
        ]
    }
    saved = abn.decode_and_save_reports(response_data, tmp_path)
    assert len(saved) == 3
    assert saved[1].read_bytes() == b"file1"


# ---------------------------------------------------------------------------
# Date-range defaults
# ---------------------------------------------------------------------------


def test_get_default_date_range_no_state() -> None:
    from datetime import datetime, timedelta

    from_str, to_str = abn.get_default_date_range(None)
    today = datetime.now().date()
    assert to_str == today.strftime("%d-%m-%Y")
    assert from_str == (today - timedelta(days=30)).strftime("%d-%m-%Y")


def test_get_default_date_range_with_last_end() -> None:
    from datetime import date

    from_str, to_str = abn.get_default_date_range(date(2026, 6, 15))
    assert from_str == "16-06-2026"  # day after last end


# ===========================================================================
# PayPal — ported protocol tests
# ===========================================================================


def test_paypal_constants() -> None:
    assert paypal.PAYPAL_BASE_URL == "https://www.paypal.com"
    assert paypal.PAYPAL_REPORTS_URL == "https://www.paypal.com/reports/dlog"
    assert paypal.PAYPAL_QL_API == "https://www.paypal.com/reports/apis/common/ql"
    assert paypal.RECENT_ACTIVITY_TEXT == "Recent activity"
    assert paypal.DEFAULT_CDP_URL == "http://127.0.0.1:9222"


def test_chrome_launch_command_contains_debug_port() -> None:
    assert "--remote-debugging-port=9222" in paypal.CHROME_LAUNCH_COMMAND
    assert "Chrome" in paypal.CHROME_LAUNCH_COMMAND


def test_to_paypal_datetime() -> None:
    from datetime import datetime

    assert paypal._to_paypal_datetime(datetime(2025, 7, 31, 22, 0, 0)) == "20250731220000"


def test_filename_from_report_url() -> None:
    url = "s3://mr-reports-1/319/Z5HUBG4GYACAS/DLOG/ONCE/2026/file.TXT"
    assert paypal._filename_from_report_url(url) == "file.TXT"


# ---------------------------------------------------------------------------
# CSRF extraction
# ---------------------------------------------------------------------------


def test_extract_csrf_from_html() -> None:
    html = """<html><body>
    <script type="application/json" id="server-data">{"_csrf": "abc123token", "other": "data"}</script>
    </body></html>"""
    assert paypal._extract_csrf_from_html(html) == "abc123token"


def test_extract_csrf_from_html_attribute_order() -> None:
    html = '<script id="server-data" type="application/json">{"_csrf": "xyz789"}</script>'
    assert paypal._extract_csrf_from_html(html) == "xyz789"


def test_extract_csrf_from_html_no_match() -> None:
    assert paypal._extract_csrf_from_html("<html><body></body></html>") is None


def test_extract_csrf_from_html_invalid_json() -> None:
    html = '<script id="server-data" type="application/json">not json</script>'
    assert paypal._extract_csrf_from_html(html) is None


def test_get_csrf_token_uses_cached_state() -> None:
    mock_page = Mock()
    state = {"csrf": "cached-token-123"}
    assert paypal._get_csrf_token(mock_page, state) == "cached-token-123"
    mock_page.request.get.assert_not_called()
    mock_page.evaluate.assert_not_called()


def test_get_csrf_token_fetches_from_reports_page() -> None:
    mock_page = Mock()
    mock_response = Mock()
    mock_response.ok = True
    mock_response.text.return_value = (
        '<script id="server-data" type="application/json">{"_csrf": "fresh-token"}</script>'
    )
    mock_page.request.get.return_value = mock_response

    state: dict = {"csrf": None}
    assert paypal._get_csrf_token(mock_page, state) == "fresh-token"
    assert state["csrf"] == "fresh-token"
    mock_page.request.get.assert_called_once_with(paypal.PAYPAL_REPORTS_URL)


def test_csrf_response_listener_extracts_token() -> None:
    """The response listener extracts _csrf from a /reports/dlog document response."""
    page = Mock()
    handlers = {}

    def _on(event, handler):
        handlers[event] = handler

    page.on.side_effect = _on

    state: dict = {"csrf": None}
    paypal._install_csrf_response_listener(page, state)
    assert "response" in handlers

    response = Mock()
    response.url = "https://www.paypal.com/reports/dlog"
    response.request.resource_type = "document"
    response.text.return_value = (
        '<script id="server-data" type="application/json">{"_csrf": "listener-token"}</script>'
    )
    handlers["response"](response)
    assert state["csrf"] == "listener-token"


def test_csrf_response_listener_ignores_other_urls() -> None:
    page = Mock()
    handlers = {}
    page.on.side_effect = lambda ev, h: handlers.update({ev: h})

    state: dict = {"csrf": None}
    paypal._install_csrf_response_listener(page, state)

    response = Mock()
    response.url = "https://www.paypal.com/other/page"
    response.request.resource_type = "document"
    handlers["response"](response)
    assert state["csrf"] is None
    response.text.assert_not_called()


# ---------------------------------------------------------------------------
# QL payloads
# ---------------------------------------------------------------------------


def _csrf_page(post_response: Mock) -> tuple[Mock, dict]:
    """Build a mock page with a pre-cached CSRF token."""
    page = Mock()
    page.context.cookies.return_value = []
    page.request.post.return_value = post_response
    return page, {"csrf": "csrf-token-value"}


def test_create_paypal_report_returns_document_id() -> None:
    mock_response = Mock()
    mock_response.ok = True
    mock_response.status = 200
    mock_response.text.return_value = '[{"document_id": "32658145554927301443020914688"}]'
    page, state = _csrf_page(mock_response)

    result = paypal.create_paypal_report(
        page, start_date="20250731220000", end_date="20260131225959", csrf_state=state
    )

    assert result == "32658145554927301443020914688"
    page.request.post.assert_called_once()
    call_kwargs = page.request.post.call_args[1]
    assert call_kwargs["headers"]["x-csrf-token"] == "csrf-token-value"
    body = json.loads(call_kwargs["data"])
    assert body["apiType"] == "reportCreate"
    assert body["reportType"] == "DLOG"
    assert body["formdata"]["start_date"] == "20250731220000"
    assert body["formdata"]["name"] == "DLOGTEMPLATE"
    assert body["formdata"]["file_format"] == "TXT"
    assert body["formdata"]["delivery_channel"] == "WEB"
    assert body["formdata"]["filters"] == "BALANCE_IMPACTING"


def test_create_paypal_report_raises_on_failure() -> None:
    mock_response = Mock()
    mock_response.ok = False
    mock_response.status = 500
    mock_response.text.return_value = "Internal Server Error"
    page, state = _csrf_page(mock_response)

    with pytest.raises(Exception, match="500"):
        paypal.create_paypal_report(page, "20250731220000", "20260131225959", csrf_state=state)


def test_create_paypal_report_raises_on_missing_document_id() -> None:
    mock_response = Mock()
    mock_response.ok = True
    mock_response.status = 200
    mock_response.text.return_value = "[{}]"
    page, state = _csrf_page(mock_response)

    with pytest.raises(Exception, match="document_id"):
        paypal.create_paypal_report(page, "20250731220000", "20260131225959", csrf_state=state)


def test_get_report_status_payload() -> None:
    mock_response = Mock()
    mock_response.ok = True
    mock_response.text.return_value = "[]"
    page, state = _csrf_page(mock_response)

    paypal._get_report_status(page, state)

    body = json.loads(page.request.post.call_args[1]["data"])
    assert body == {"apiType": "reports", "reportType": "DLOG", "isAdmin": False}


def test_download_paypal_report_returns_binary_content() -> None:
    mock_response = Mock()
    mock_response.ok = True
    mock_response.headers = {"content-type": "text/plain"}
    mock_response.body.return_value = b"raw file content"
    page, state = _csrf_page(mock_response)

    result = paypal.download_paypal_report(page, ["s3://bucket/report.TXT"], state)

    assert result == b"raw file content"
    body = json.loads(page.request.post.call_args[1]["data"])
    assert body["apiType"] == "download"
    assert body["reportNames"] == ["s3://bucket/report.TXT"]
    assert body["reportType"] == "DLOG"


def test_download_paypal_report_decodes_base64_json() -> None:
    content = b"test file bytes"
    payload = [{"fileBytes": base64.b64encode(content).decode()}]
    mock_response = Mock()
    mock_response.ok = True
    mock_response.headers = {"content-type": "application/json"}
    mock_response.body.return_value = json.dumps(payload).encode()
    page, state = _csrf_page(mock_response)

    result = paypal.download_paypal_report(page, ["s3://bucket/report.TXT"], state)
    assert result == content


def test_download_paypal_report_raises_on_failure() -> None:
    mock_response = Mock()
    mock_response.ok = False
    mock_response.status = 403
    mock_response.body.return_value = b"Forbidden"
    page, state = _csrf_page(mock_response)

    with pytest.raises(Exception, match="403"):
        paypal.download_paypal_report(page, ["s3://x"], state)


# ---------------------------------------------------------------------------
# Polling (fast: zero waits)
# ---------------------------------------------------------------------------


def _poll_registry() -> JobRegistry:
    reg = JobRegistry()
    reg.create("paypal")
    return reg


def test_poll_report_status_returns_urls_when_available() -> None:
    status_payload = [
        {
            "reportDetails": [
                {
                    "documentGenId": "12345",
                    "status": "AVAILABLE",
                    "downloadUrls": ["s3://bucket/report.TXT"],
                }
            ]
        }
    ]
    mock_response = Mock()
    mock_response.ok = True
    mock_response.text.return_value = json.dumps(status_payload)
    page, state = _csrf_page(mock_response)

    urls = paypal.poll_report_status(
        page, "12345", state, _poll_registry(), poll_interval=0, initial_wait=0
    )
    assert urls == ["s3://bucket/report.TXT"]


def test_poll_report_status_polls_until_available() -> None:
    processing = [
        {"reportDetails": [{"documentGenId": "12345", "status": "PROCESSING"}]}
    ]
    available = [
        {
            "reportDetails": [
                {
                    "documentGenId": "12345",
                    "status": "AVAILABLE",
                    "downloadUrls": ["s3://bucket/r.TXT"],
                }
            ]
        }
    ]
    responses = []
    for payload in (processing, processing, available):
        r = Mock()
        r.ok = True
        r.text.return_value = json.dumps(payload)
        responses.append(r)

    page = Mock()
    page.context.cookies.return_value = []
    page.request.post.side_effect = responses
    state = {"csrf": "t"}

    reg = _poll_registry()
    urls = paypal.poll_report_status(page, "12345", state, reg, poll_interval=0, initial_wait=0)
    assert urls == ["s3://bucket/r.TXT"]
    assert page.request.post.call_count == 3
    # Poll progress surfaced in job status.
    assert "PROCESSING" in reg.get("paypal").message


def test_poll_report_status_keeps_polling_when_not_indexed() -> None:
    not_indexed = [{"reportDetails": [{"documentGenId": "other", "status": "AVAILABLE"}]}]
    available = [
        {
            "reportDetails": [
                {"documentGenId": "12345", "status": "AVAILABLE", "downloadUrls": ["s3://b/r.TXT"]}
            ]
        }
    ]
    responses = []
    for payload in (not_indexed, available):
        r = Mock()
        r.ok = True
        r.text.return_value = json.dumps(payload)
        responses.append(r)

    page = Mock()
    page.context.cookies.return_value = []
    page.request.post.side_effect = responses
    state = {"csrf": "t"}

    urls = paypal.poll_report_status(
        page, "12345", state, _poll_registry(), poll_interval=0, initial_wait=0
    )
    assert urls == ["s3://b/r.TXT"]


def test_poll_report_status_raises_on_available_without_urls() -> None:
    payload = [
        {"reportDetails": [{"documentGenId": "12345", "status": "AVAILABLE", "downloadUrls": []}]}
    ]
    mock_response = Mock()
    mock_response.ok = True
    mock_response.text.return_value = json.dumps(payload)
    page, state = _csrf_page(mock_response)

    with pytest.raises(Exception, match="no downloadUrls"):
        paypal.poll_report_status(
            page, "12345", state, _poll_registry(), poll_interval=0, initial_wait=0
        )


def test_poll_report_status_raises_on_empty_response() -> None:
    mock_response = Mock()
    mock_response.ok = True
    mock_response.text.return_value = "[]"
    page, state = _csrf_page(mock_response)

    with pytest.raises(Exception, match="Unexpected status response"):
        paypal.poll_report_status(
            page, "12345", state, _poll_registry(), poll_interval=0, initial_wait=0
        )


# ---------------------------------------------------------------------------
# XHR headers
# ---------------------------------------------------------------------------


def test_xhr_headers_include_csrf_and_cookies() -> None:
    page = Mock()
    page.context.cookies.return_value = [
        {"name": "a", "value": "1"},
        {"name": "b", "value": "2"},
    ]
    headers = paypal._xhr_headers(page, "tok")
    assert headers["x-csrf-token"] == "tok"
    assert headers["Cookie"] == "a=1; b=2"
    assert headers["Origin"] == paypal.PAYPAL_BASE_URL
    assert headers["Referer"] == paypal.PAYPAL_REPORTS_URL
    assert headers["X-Requested-With"] == "XMLHttpRequest"


def test_xhr_headers_without_cookies() -> None:
    page = Mock()
    page.context.cookies.return_value = []
    headers = paypal._xhr_headers(page, "tok")
    assert "Cookie" not in headers


# ===========================================================================
# Job runner failure paths (no Playwright browsers involved)
# ===========================================================================


def test_run_paypal_job_invalid_dates_fails_fast(settings) -> None:
    reg = JobRegistry()
    reg.create("paypal")
    paypal.run_paypal_job(reg, settings, "bad-date", "2026-01-01")
    job = reg.get("paypal")
    assert job.state == JobState.FAILED
    assert "Invalid date" in job.message


def test_run_paypal_job_cdp_unreachable_fails_with_launch_command(settings) -> None:
    """CDP connect failure -> fail fast, message contains the exact Chrome command."""
    reg = JobRegistry()
    reg.create("paypal")
    # Nothing listens on this port.
    paypal.run_paypal_job(
        reg, settings, "2026-01-01", "2026-06-30", cdp_url="http://127.0.0.1:59999"
    )
    job = reg.get("paypal")
    assert job.state == JobState.FAILED
    assert "--remote-debugging-port=9222" in job.message
    assert "Could not connect to Chrome" in job.message
