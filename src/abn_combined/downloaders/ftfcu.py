"""First Tech Federal Credit Union download worker — attaches to the user's
real Chrome over CDP after the user logs in.

Protocol (see protocol/firsttechfed.com-protocol.md): the login page has a
Cloudflare Turnstile challenge. Turnstile does not complete while a Playwright
client with init scripts is attached, so this job does not attach before the
login. It finds or opens the First Tech tab over plain HTTP (``/json/list``,
``/json/new``), and polls ``/json/list`` until the tab shows the account
overview. Only then does it attach with ``connect_over_cdp``.

After the login, one multipart POST to ``/MyAccountsV2/Export`` with
``format=56`` returns one OFX file for all accounts. The anti-forgery token
and the account GUIDs come from ``#export_form`` on the logged-in page.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from ..core.jobs import JobRegistry, JobState
from ..logging_config import get_logger
from .abn import _update_download_state
from .browser import (
    DEFAULT_CDP_URL,
    connect_failure_message,
    identify_cdp_endpoint,
    missing_playwright_message,
    no_contexts_message,
)

if TYPE_CHECKING:
    from ..settings import Settings

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

FTFCU_ACCOUNTS_URL = "https://banking.firsttechfed.com/MyAccountsV2"
FTFCU_EXPORT_URL = "https://banking.firsttechfed.com/MyAccountsV2/Export"
FTFCU_HOST = "banking.firsttechfed.com"
OFX_FORMAT = "56"

_AUTH_TIMEOUT_SECONDS = 5 * 60  # 5 minutes (password + MFA)
_AUTH_POLL_SECONDS = 3
_FORM_TIMEOUT_MS = 30_000

# The bank refuses transactions older than two years.
_MAX_HISTORY_YEARS = 2

_READ_FORM_JS = """() => {
  const f = document.querySelector('#export_form');
  if (!f) return null;
  const token = f.querySelector('input[name=__RequestVerificationToken]');
  return {
    token: token ? token.value : null,
    accounts: [...f.querySelectorAll('input[name=AccountIdentifiers]')].map(e => {
      const label = e.parentElement && e.parentElement.querySelector('label');
      const row = e.closest('.row');
      return {
        guid: e.value,
        name: label ? (label.getAttribute('aria-label') || '').replace(/^Checkbox for /, '') : '',
        text: row ? row.innerText.replace(/\\s+/g, ' ').trim() : '',
      };
    }),
  };
}"""


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def is_accounts_url(url: str) -> bool:
    """True when *url* is the logged-in account overview (not the login page)."""
    return is_ftfcu_url(url) and url.lower().startswith(FTFCU_ACCOUNTS_URL.lower())


def clamp_range(from_date: str, to_date: str, today: date | None = None) -> tuple[str, str]:
    """Validate a YYYY-MM-DD range and clamp it to what the bank accepts.

    The start moves forward to two years before today. The end moves back to
    today. Raises ``ValueError`` for a malformed date or an inverted range.
    """
    today = today or date.today()
    start = datetime.strptime(from_date, "%Y-%m-%d").date()
    end = datetime.strptime(to_date, "%Y-%m-%d").date()
    try:
        earliest = today.replace(year=today.year - _MAX_HISTORY_YEARS)
    except ValueError:  # 29 February
        earliest = today.replace(year=today.year - _MAX_HISTORY_YEARS, day=28)
    start = max(start, earliest)
    end = min(end, today)
    if start > end:
        raise ValueError(f"start date {start} is after end date {end}")
    return start.isoformat(), end.isoformat()


def build_export_body(
    token: str,
    account_guids: list[str],
    from_date: str,
    to_date: str,
    today: str,
    boundary: str,
) -> bytes:
    """Build the multipart body of the export POST, in the field order of the UI.

    ``AccountIdentifiers`` repeats once for each account, so a dict-based
    multipart helper cannot build this body.
    """
    parts = [
        ("__RequestVerificationToken", token),
        ("Parameters.TransactionCategoryId", ""),
        ("Parameters.Debit", ""),
        ("Parameters.Description", ""),
        ("Parameters.MaximumAmount", "-1"),
        ("Parameters.MinimumAmount", ""),
        ("Parameters.TransactionTypeId", ""),
        ("Parameters.StartCheckNumber", ""),
        ("Parameters.EndCheckNumber", ""),
        ("format", OFX_FORMAT),
        ("Parameters.StartDate", from_date),
        ("Parameters.EndDate", to_date),
        ("Parameters.TodaysDate", today),
    ] + [("AccountIdentifiers", guid) for guid in account_guids]
    body = "".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        for name, value in parts
    )
    return (body + f"--{boundary}--\r\n").encode("utf-8")


def count_ofx_transactions(body: bytes) -> int:
    """Number of ``<STMTTRN>`` records in an OFX body."""
    return body.upper().count(b"<STMTTRN>")


# ---------------------------------------------------------------------------
# CDP HTTP endpoints (no websocket attach, so Turnstile is not disturbed)
# ---------------------------------------------------------------------------


def list_page_targets(cdp_url: str) -> list[dict]:
    """The ``page`` targets from ``<cdp_url>/json/list``."""
    with urllib.request.urlopen(f"{cdp_url.rstrip('/')}/json/list", timeout=5) as resp:
        targets = json.loads(resp.read().decode("utf-8"))
    return [t for t in targets if t.get("type") == "page"]


def open_tab(cdp_url: str, url: str) -> None:
    """Open a new tab at *url* with ``PUT /json/new`` (no automation attach)."""
    req = urllib.request.Request(
        f"{cdp_url.rstrip('/')}/json/new?{urllib.parse.quote(url, safe=':/')}",
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=5):
        pass


def is_ftfcu_url(url: str) -> bool:
    """True for an https page on the First Tech host (not a ``blob:`` download tab)."""
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == FTFCU_HOST


def _has_ftfcu_tab(targets: list[dict]) -> bool:
    return any(is_ftfcu_url(t.get("url") or "") for t in targets)


def _has_accounts_tab(targets: list[dict]) -> bool:
    return any(is_accounts_url(t.get("url") or "") for t in targets)


# ---------------------------------------------------------------------------
# Job runner (executed in a worker thread)
# ---------------------------------------------------------------------------


def run_ftfcu_job(
    registry: JobRegistry,
    settings: Settings,
    from_date: str,
    to_date: str,
    cdp_url: str = DEFAULT_CDP_URL,
) -> None:
    """Worker function — runs in a dedicated thread.

    Updates registry state:
    pending → waiting-for-auth → downloading → importing → done/failed.
    """
    source = "ftfcu"
    browser = None

    def _fail(msg: str) -> None:
        registry.update_state(source, JobState.FAILED, msg)
        # Detach only. The tab belongs to the user's login, so keep it open.
        if browser is not None:
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass

    try:
        from_date, to_date = clamp_range(from_date, to_date)
    except ValueError as exc:
        _fail(f"Invalid date range: {exc}")
        return

    registry.update_state(
        source,
        JobState.WAITING_FOR_AUTH,
        f"Connecting to Chrome at {cdp_url}…",
    )

    if identify_cdp_endpoint(cdp_url) is None:
        _fail(
            connect_failure_message(
                cdp_url, ConnectionError("no answer on /json/version"), FTFCU_ACCOUNTS_URL
            )
        )
        return

    try:
        # Wait for the login over plain HTTP. A Playwright attach during the
        # login stops the Cloudflare Turnstile challenge.
        targets = list_page_targets(cdp_url)
        if not _has_ftfcu_tab(targets):
            open_tab(cdp_url, FTFCU_ACCOUNTS_URL)
        registry.update_state(
            source,
            JobState.WAITING_FOR_AUTH,
            "Log in to First Tech in the Chrome window. The job waits for the login…",
        )
        deadline = time.monotonic() + _AUTH_TIMEOUT_SECONDS
        while not _has_accounts_tab(list_page_targets(cdp_url)):
            if time.monotonic() > deadline:
                _fail("Login timeout. Start the download again, and log in to First Tech within 5 minutes.")
                return
            time.sleep(_AUTH_POLL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        _fail(connect_failure_message(cdp_url, exc, FTFCU_ACCOUNTS_URL))
        return

    try:
        # Imports live inside the try so a broken Playwright install fails
        # the job instead of leaving it stuck forever.
        from playwright.sync_api import sync_playwright

        from ..core.importer import ImportError_, import_file
        from ..db import get_session_factory

        with sync_playwright() as pw:
            try:
                browser = pw.chromium.connect_over_cdp(cdp_url)
            except Exception as exc:  # noqa: BLE001
                _fail(connect_failure_message(cdp_url, exc, FTFCU_ACCOUNTS_URL))
                return

            if not browser.contexts:
                _fail(no_contexts_message(cdp_url))
                return

            context = browser.contexts[0]
            page = next((p for p in context.pages if is_accounts_url(p.url)), None)
            if page is None:
                _fail("The First Tech account overview is closed. Log in again, and start the download again.")
                return

            # The page JavaScript adds the export form after the load. The
            # drawer is hidden, so wait for "attached", not "visible".
            try:
                page.wait_for_selector("#export_form", state="attached", timeout=_FORM_TIMEOUT_MS)
            except Exception:  # noqa: BLE001
                _fail(
                    "The First Tech page has no export form. Reload the account overview. "
                    "Log in again if the bank asks, and start the download again."
                )
                return
            form = page.evaluate(_READ_FORM_JS)
            if not form or not form.get("token") or not form.get("accounts"):
                _fail("Could not read the token or the accounts from the First Tech page.")
                return

            accounts = form["accounts"]
            logger.info("ftfcu_authenticated", accounts=len(accounts))
            registry.update_state(
                source,
                JobState.DOWNLOADING,
                f"Downloading OFX for {len(accounts)} account(s) from First Tech…",
            )

            boundary = "----dvmfinance" + uuid.uuid4().hex
            body = build_export_body(
                form["token"],
                [a["guid"] for a in accounts],
                from_date,
                to_date,
                date.today().isoformat(),
                boundary,
            )
            try:
                resp = context.request.post(
                    FTFCU_EXPORT_URL,
                    data=body,
                    headers={
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                        "Accept": "application/json, text/plain, */*",
                        "Referer": FTFCU_ACCOUNTS_URL,
                    },
                )
                content_type = resp.headers.get("content-type", "")
                if not resp.ok or "ofx" not in content_type:
                    _fail(
                        f"First Tech export failed with status {resp.status} "
                        f"({content_type or 'no content type'}). "
                        "The session can be expired. Reload the page, log in, and start the download again."
                    )
                    return
                ofx = resp.body()
            except Exception as exc:  # noqa: BLE001
                _fail(f"Download failed: {exc}")
                return
            finally:
                # Detach only. close() on a CDP-connected browser leaves the
                # user's Chrome and the logged-in tab open.
                try:
                    browser.close()
                    browser = None
                except Exception:  # noqa: BLE001
                    pass

            to_ddmmyyyy = datetime.strptime(to_date, "%Y-%m-%d").strftime("%d-%m-%Y")
            n_records = count_ofx_transactions(ofx)
            session_factory = get_session_factory()

            if n_records == 0:
                with session_factory() as db:
                    _update_download_state(db, source, None, to_ddmmyyyy)
                registry.set_summary(
                    source,
                    {"files": [], "new": 0, "duplicates": 0, "categorized": 0,
                     "uncategorized": 0, "failed_files": []},
                )
                registry.update_state(
                    source,
                    JobState.DONE,
                    f"Done — First Tech has no transactions from {from_date} to {to_date}.",
                )
                return

            settings.statements_dir.mkdir(parents=True, exist_ok=True)
            dest = settings.statements_dir / f"ftfcu-{from_date}-{to_date}.ofx"
            dest.write_bytes(ofx)
            logger.info("ftfcu_file_saved", path=str(dest), records=n_records)

            # --- Import phase ---
            registry.update_state(source, JobState.IMPORTING, "Importing 1 file…")
            with session_factory() as db:
                try:
                    summary = import_file(
                        db, ofx, dest.name, settings.statements_dir, fmt="ftfcu"
                    ).as_dict()
                except ImportError_ as exc:
                    logger.warning("ftfcu_import_failed", file=dest.name, error=str(exc))
                    _fail(f"Import failed for {dest.name}: {exc}")
                    return
                _update_download_state(db, source, None, to_ddmmyyyy)

            registry.set_summary(
                source,
                {
                    "files": [summary["source_file"]],
                    "new": summary["new"],
                    "duplicates": summary["duplicates"],
                    "categorized": summary["categorized"],
                    "uncategorized": summary["uncategorized"],
                    "failed_files": [],
                },
            )
            registry.update_state(
                source,
                JobState.DONE,
                f"Done — {summary['new']} new transaction(s) imported "
                f"from {len(accounts)} First Tech account(s).",
            )

    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, ModuleNotFoundError) and exc.name == "playwright":
            _fail(missing_playwright_message())
            logger.warning("ftfcu_job_playwright_missing")
            return
        _fail(f"Unexpected error: {exc}")
        logger.exception("ftfcu_job_unexpected_error", error=str(exc))
