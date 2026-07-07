"""PayPal download worker — ported from abn-download/paypal_download.py.

Protocol code is kept diff-able against the source; only CLI-specific parts
(argparse, interactive countdown, upload_utils) are replaced by job-registry
callbacks and the import pipeline.

Key design note from the source:
  - Connect to an existing Chrome instance launched with --remote-debugging-port=9222
    (CDP mode) rather than launching a fresh browser — avoids anti-bot detection.
  - CSRF token is extracted from the /reports/dlog HTML response before the SPA
    removes the <script id="server-data"> tag.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.jobs import JobRegistry, JobState
from ..logging_config import get_logger

if TYPE_CHECKING:
    from ..settings import Settings

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Protocol constants (ported verbatim)
# ---------------------------------------------------------------------------

PAYPAL_BASE_URL = "https://www.paypal.com"
PAYPAL_REPORTS_URL = "https://www.paypal.com/reports/dlog"
DEFAULT_CDP_URL = "http://127.0.0.1:9222"
PAYPAL_QL_API = "https://www.paypal.com/reports/apis/common/ql"
RECENT_ACTIVITY_TEXT = "Recent activity"
INITIAL_STATUS_WAIT_SECONDS = 20
POLL_RETRY_WAIT_SECONDS = 60
MAX_RESPONSE_LOG_BYTES = 500
NAVIGATION_DELAY_SECONDS = 2

# Exact Chrome launch command shown to the user when CDP connection fails.
CHROME_LAUNCH_COMMAND = (
    "/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome "
    "--remote-debugging-port=9222 --user-data-dir=~/.chrome/debugdir "
    "https://www.paypal.com/reports/dlog"
)

# Thread-local CSRF cache (reset per job run).
_csrf_token: str | None = None


# ---------------------------------------------------------------------------
# Ported pure / near-pure functions
# ---------------------------------------------------------------------------


def _extract_csrf_from_html(html_body: str) -> str | None:
    """Extract _csrf from server-data script in raw HTML (before page JS removes it)."""
    match = re.search(
        r'<script[^>]*(?:id="server-data"[^>]*type="application/json"|'
        r'type="application/json"[^>]*id="server-data")[^>]*>([\s\S]*?)</script>',
        html_body,
    )
    if not match:
        match = re.search(
            r'<script[^>]+id="server-data"[^>]*>([\s\S]*?)</script>',
            html_body,
        )
    if match:
        try:
            data = json.loads(match.group(1))
            return data.get("_csrf") if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
    return None


def _install_csrf_response_listener(page, state: dict) -> None:
    """Install response listener to intercept /reports/dlog HTML and extract CSRF token.

    *state* is a mutable dict (``{"csrf": None}``) shared between the listener closure
    and the caller — avoids module-level global state between jobs.
    """

    def on_response(response) -> None:
        if state.get("csrf"):
            return
        url = response.url
        if "/reports/dlog" not in url:
            return
        if response.request.resource_type != "document":
            return
        try:
            body = response.text()
            token = _extract_csrf_from_html(body)
            if token:
                state["csrf"] = token
        except Exception:  # noqa: BLE001
            pass

    page.on("response", on_response)


def _get_csrf_token(page, state: dict) -> str:
    """Return cached CSRF token or fetch fresh from /reports/dlog."""
    if state.get("csrf"):
        return state["csrf"]

    # Fetch explicitly — CDP may not deliver cached response body to the listener.
    try:
        response = page.request.get(PAYPAL_REPORTS_URL)
        if response.ok:
            token = _extract_csrf_from_html(response.text())
            if token:
                state["csrf"] = token
                return token
    except Exception as exc:  # noqa: BLE001
        logger.warning("paypal_csrf_fetch_failed", error=str(exc))

    # DOM fallback (may fail if SPA already removed the tag).
    token = _extract_csrf_token_dom(page)
    state["csrf"] = token
    return token


def _extract_csrf_token_dom(page) -> str:
    """Extract CSRF from DOM (last resort; SPA may have removed it)."""
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:  # noqa: BLE001
        pass
    time.sleep(1)

    token = page.evaluate("""() => {
        const serverData = document.querySelector('script[type="application/json"]#server-data');
        if (serverData) {
            try {
                const data = JSON.parse(serverData.textContent);
                const t = data?._csrf;
                if (t) return t;
            } catch (_) {}
        }
        const meta = document.querySelector('meta[name="csrf-token"]') ||
            document.querySelector('meta[name="x-csrf-token"]') ||
            document.querySelector('meta[property="csrf-token"]');
        if (meta && meta.getAttribute('content')) return meta.getAttribute('content');
        const cookieMatch = document.cookie.match(/(?:csrf[_-]?token|x-csrf-token|_csrf)=([^;]+)/i);
        if (cookieMatch) return decodeURIComponent(cookieMatch[1].trim());
        return null;
    }""")
    if not token:
        raise Exception(
            "Could not extract PayPal CSRF token. "
            "Ensure you are logged in to PayPal in the connected Chrome window."
        )
    return token


def _xhr_headers(page, csrf_token: str) -> dict:
    """Build headers for PayPal XHR requests."""
    cookies = page.context.cookies(PAYPAL_BASE_URL)
    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies) if cookies else ""
    headers = {
        "Referer": PAYPAL_REPORTS_URL,
        "Origin": PAYPAL_BASE_URL,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "X-Requested-With": "XMLHttpRequest",
        "x-csrf-token": csrf_token,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/26.2 Safari/605.1.15"
        ),
    }
    if cookie_str:
        headers["Cookie"] = cookie_str
    return headers


def _to_paypal_datetime(dt: datetime) -> str:
    """Convert datetime to PayPal format YYYYMMDDHHmmss."""
    return dt.strftime("%Y%m%d%H%M%S")


def create_paypal_report(
    page,
    start_date: str,
    end_date: str,
    csrf_state: dict,
    file_format: str = "TXT",
    filters: str = "BALANCE_IMPACTING",
) -> str:
    """Create a PayPal report via XHR. Returns document_id."""
    csrf_token = _get_csrf_token(page, csrf_state)
    headers = _xhr_headers(page, csrf_token)
    payload = {
        "apiType": "reportCreate",
        "formdata": {
            "start_date": start_date,
            "end_date": end_date,
            "name": "DLOGTEMPLATE",
            "file_format": file_format,
            "delivery_channel": "WEB",
            "filters": filters,
        },
        "isAdmin": None,
        "reportType": "DLOG",
    }
    body = json.dumps(payload)
    response = page.request.post(PAYPAL_QL_API, headers=headers, data=body)
    response_text = response.text()
    if not response.ok:
        raise Exception(
            f"PayPal reportCreate failed with status {response.status}: {response_text}"
        )
    data = json.loads(response_text)
    if not isinstance(data, list) or not data:
        raise Exception(f"Unexpected reportCreate response: {response_text}")
    document_id = data[0].get("document_id")
    if not document_id:
        raise Exception(f"No document_id in reportCreate response: {response_text}")
    return str(document_id)


def _get_report_status(page, csrf_state: dict) -> list:
    """Fetch report status list from PayPal API."""
    csrf_token = _get_csrf_token(page, csrf_state)
    headers = _xhr_headers(page, csrf_token)
    payload = {"apiType": "reports", "reportType": "DLOG", "isAdmin": False}
    body = json.dumps(payload)
    response = page.request.post(PAYPAL_QL_API, headers=headers, data=body)
    if not response.ok:
        raise Exception(
            f"PayPal reports poll failed with status {response.status}: {response.text()}"
        )
    return json.loads(response.text())


def poll_report_status(
    page,
    document_id: str,
    csrf_state: dict,
    registry: JobRegistry,
    source: str = "paypal",
    poll_interval: int = POLL_RETRY_WAIT_SECONDS,
    initial_wait: int = INITIAL_STATUS_WAIT_SECONDS,
) -> list[str]:
    """Poll until the report is AVAILABLE. Returns downloadUrls list.

    Replaces the interactive countdown from the source with a plain sleep +
    job-status message updates.
    """
    time.sleep(initial_wait)

    poll_count = 0
    while True:
        data = _get_report_status(page, csrf_state)
        if not isinstance(data, list) or not data:
            raise Exception(f"Unexpected status response: {data}")

        entry = None
        for batch in data:
            for d in batch.get("reportDetails", []):
                if str(d.get("documentGenId", "")) == str(document_id):
                    entry = d
                    break
            if entry:
                break

        if not entry:
            poll_count += 1
            msg = f"Report not yet indexed (poll #{poll_count}). Waiting {poll_interval}s…"
            registry.update_state(source, JobState.DOWNLOADING, msg)
            time.sleep(poll_interval)
            continue

        status = entry.get("status", "")
        if status == "AVAILABLE":
            urls = entry.get("downloadUrls", [])
            if not urls:
                raise Exception(f"Report available but no downloadUrls: {entry}")
            return list(urls)

        poll_count += 1
        msg = f"Report status: {status} (poll #{poll_count}). Waiting {poll_interval}s…"
        registry.update_state(source, JobState.DOWNLOADING, msg)
        time.sleep(poll_interval)


def download_paypal_report(page, report_names: list[str], csrf_state: dict) -> bytes:
    """Download report content via XHR. Returns raw file bytes."""
    import base64 as _base64

    csrf_token = _get_csrf_token(page, csrf_state)
    headers = _xhr_headers(page, csrf_token)
    payload = {
        "apiType": "download",
        "reportNames": report_names,
        "reportType": "DLOG",
    }
    body = json.dumps(payload)
    response = page.request.post(PAYPAL_QL_API, headers=headers, data=body)
    body_bytes = response.body()

    if not response.ok:
        raise Exception(
            f"PayPal download failed with status {response.status}: {body_bytes[:500]!r}"
        )

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            response_text = body_bytes.decode("utf-8")
            data = json.loads(response_text)
            if isinstance(data, list) and data:
                first = data[0] if isinstance(data[0], dict) else {}
                if "fileBytes" in first:
                    return _base64.b64decode(first["fileBytes"])
                if "fileContent" in first:
                    return _base64.b64decode(first["fileContent"])
            if isinstance(data, dict):
                if "fileBytes" in data:
                    return _base64.b64decode(data["fileBytes"])
                if "fileContent" in data:
                    return _base64.b64decode(data["fileContent"])
        except (json.JSONDecodeError, KeyError, UnicodeDecodeError):
            pass

    return body_bytes


def _filename_from_report_url(url: str) -> str:
    """Extract filename from S3-style report URL."""
    parts = url.split("/")
    return parts[-1] if parts else "paypal_report.txt"


# ---------------------------------------------------------------------------
# Job runner (executed in a worker thread)
# ---------------------------------------------------------------------------


def run_paypal_job(
    registry: JobRegistry,
    settings: Settings,
    start_date: str,
    end_date: str,
    cdp_url: str = DEFAULT_CDP_URL,
) -> None:
    """Worker function — runs in a dedicated thread.

    Updates registry state:
    pending → waiting-for-auth → downloading → importing → done/failed.

    On CDP connection failure, fails immediately with the exact Chrome launch command.
    """
    from playwright.sync_api import sync_playwright

    from ..core.importer import ImportError_, import_file
    from ..db import get_session_factory

    source = "paypal"
    browser = None

    def _fail(msg: str) -> None:
        registry.update_state(source, JobState.FAILED, msg)
        if browser is not None:
            try:
                browser.disconnect()
            except Exception:  # noqa: BLE001
                pass

    # Convert date strings (YYYY-MM-DD) to PayPal datetime format.
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(
            hour=0, minute=0, second=0
        )
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )
    except ValueError as exc:
        _fail(f"Invalid date format: {exc}")
        return

    paypal_start = _to_paypal_datetime(start_dt)
    paypal_end = _to_paypal_datetime(end_dt)

    registry.update_state(
        source,
        JobState.WAITING_FOR_AUTH,
        f"Connecting to Chrome at {cdp_url}…",
    )

    try:
        with sync_playwright() as pw:
            # Fail fast if CDP Chrome is not running.
            try:
                browser = pw.chromium.connect_over_cdp(cdp_url)
            except Exception as exc:  # noqa: BLE001
                _fail(
                    f"Could not connect to Chrome at {cdp_url}. "
                    f"Please start Chrome with:\n{CHROME_LAUNCH_COMMAND}\n\nError: {exc}"
                )
                return

            if not browser.contexts:
                _fail(
                    "Connected Chrome has no open contexts. "
                    "Ensure Chrome was started with --remote-debugging-port=9222."
                )
                return

            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()

            csrf_state: dict = {"csrf": None}
            _install_csrf_response_listener(page, csrf_state)

            # Navigate to PayPal home so login detection works.
            page.goto(PAYPAL_BASE_URL, wait_until="load", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:  # noqa: BLE001
                pass

            registry.update_state(
                source,
                JobState.WAITING_FOR_AUTH,
                "Waiting for PayPal login (check the Chrome window)…",
            )

            # Wait for "Recent activity" text — indicates user is logged in.
            try:
                page.wait_for_selector(
                    f"text={RECENT_ACTIVITY_TEXT}", timeout=5 * 60 * 1_000
                )
            except Exception as exc:  # noqa: BLE001
                _fail(f"PayPal login timeout: {exc}")
                return

            time.sleep(NAVIGATION_DELAY_SECONDS)
            page.goto(PAYPAL_REPORTS_URL, wait_until="load", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:  # noqa: BLE001
                pass

            registry.update_state(
                source, JobState.DOWNLOADING, "Creating PayPal report…"
            )

            try:
                document_id = create_paypal_report(
                    page, paypal_start, paypal_end, csrf_state
                )
                logger.info("paypal_report_created", document_id=document_id)
            except Exception as exc:  # noqa: BLE001
                _fail(f"Failed to create PayPal report: {exc}")
                return

            registry.update_state(
                source,
                JobState.DOWNLOADING,
                f"Waiting for report {document_id} to be ready…",
            )

            try:
                download_urls = poll_report_status(
                    page, document_id, csrf_state, registry
                )
            except Exception as exc:  # noqa: BLE001
                _fail(f"Polling failed: {exc}")
                return

            # Download and save files.
            statements_dir = settings.statements_dir
            statements_dir.mkdir(parents=True, exist_ok=True)
            saved_files: list[Path] = []

            for url in download_urls:
                try:
                    content = download_paypal_report(page, [url], csrf_state)
                    filename = _filename_from_report_url(url)
                    dest = statements_dir / filename
                    dest.write_bytes(content)
                    saved_files.append(dest)
                    logger.info("paypal_file_saved", path=str(dest))
                except Exception as exc:  # noqa: BLE001
                    _fail(f"Download failed for {url}: {exc}")
                    return

            # Disconnect (user's Chrome stays open).
            try:
                browser.disconnect()
                browser = None
            except Exception:  # noqa: BLE001
                pass

            if not saved_files:
                _fail("No PayPal report files were downloaded.")
                return

            # --- Import phase ---
            registry.update_state(
                source, JobState.IMPORTING, f"Importing {len(saved_files)} file(s)…"
            )

            summaries = []
            failed_files = []
            session_factory = get_session_factory()
            with session_factory() as db:
                for path in saved_files:
                    try:
                        summary = import_file(
                            db,
                            path.read_bytes(),
                            path.name,
                            statements_dir,
                            fmt="paypal",
                        )
                        summaries.append(summary.as_dict())
                        logger.info(
                            "paypal_file_imported", file=path.name, new=summary.new
                        )
                    except ImportError_ as exc:
                        logger.warning(
                            "paypal_import_failed", file=path.name, error=str(exc)
                        )
                        failed_files.append(f"{path.name}: {exc}")

                # Update download_state.
                _update_download_state(db, "paypal", None, end_date)

            aggregate = {
                "files": [s["source_file"] for s in summaries],
                "new": sum(s["new"] for s in summaries),
                "duplicates": sum(s["duplicates"] for s in summaries),
                "categorized": sum(s["categorized"] for s in summaries),
                "uncategorized": sum(s["uncategorized"] for s in summaries),
                "failed_files": failed_files,
            }
            registry.set_summary(source, aggregate)
            registry.update_state(
                source,
                JobState.DONE,
                f"Done — {aggregate['new']} new transaction(s) imported from {len(saved_files)} file(s).",
            )

    except Exception as exc:  # noqa: BLE001
        _fail(f"Unexpected error: {exc}")
        logger.exception("paypal_job_unexpected_error", error=str(exc))


def _update_download_state(db, source: str, account: str | None, end_date_str: str) -> None:
    """Upsert the DownloadState bookmark for *source/account*."""
    from sqlalchemy import select

    from ..core.models import DownloadState

    try:
        end = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except ValueError:
        return

    stmt = select(DownloadState).where(
        DownloadState.source == source,
        DownloadState.account == account,
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        row = DownloadState(source=source, account=account)
        db.add(row)
    row.last_success_at = datetime.utcnow()
    row.last_range_end = end
    db.commit()
