"""Wise download worker — attaches to the user's real Chrome over CDP.

Protocol (see protocol/wise.com-protocol.md): the logged-in wise.com session
is cookie-authenticated; API calls add a static, public
``x-access-token: Tr4n5f3rw153`` header. The profile id is embedded in the
/all-transactions SSR HTML, and the CSV statement comes from a single POST to
the activities export endpoint.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

from ..core.jobs import JobRegistry, JobState
from ..logging_config import get_logger
from .abn import _update_download_state
from .browser import DEFAULT_CDP_URL, connect_failure_message, no_contexts_message

if TYPE_CHECKING:
    from ..settings import Settings

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

WISE_TRANSACTIONS_URL = "https://wise.com/all-transactions"
WISE_EXPORT_URL = (
    "https://wise.com/gateway/v1/profiles/{profile_id}/activities/list/export/"
)
# Static token shipped in the Wise web app — public, not a secret.
WISE_ACCESS_TOKEN = "Tr4n5f3rw153"

_AUTH_TIMEOUT_MS = 5 * 60 * 1_000  # 5 minutes
_AUTH_POLL_SECONDS = 2
_EXPORT_MAX_ROWS = 10_000


def extract_profile_id(html: str) -> str | None:
    """Extract the numeric profile id from wise.com SSR HTML."""
    m = re.search(r'"profileId":(\d+)', html)
    return m.group(1) if m else None


def _iso_range(from_date: str, to_date: str) -> tuple[str, str]:
    """YYYY-MM-DD pair → ISO instants covering the full days (UTC)."""
    # Validates the inputs as a side effect.
    datetime.strptime(from_date, "%Y-%m-%d")
    datetime.strptime(to_date, "%Y-%m-%d")
    return f"{from_date}T00:00:00.000Z", f"{to_date}T23:59:59.999Z"


# ---------------------------------------------------------------------------
# Job runner (executed in a worker thread)
# ---------------------------------------------------------------------------


def run_wise_job(
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
    source = "wise"
    browser = None
    page = None

    def _fail(msg: str) -> None:
        registry.update_state(source, JobState.FAILED, msg)
        # Close the tab we opened (never the user's Chrome), then detach.
        if page is not None:
            try:
                page.close()
            except Exception:  # noqa: BLE001
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass

    try:
        since, until = _iso_range(from_date, to_date)
    except ValueError as exc:
        _fail(f"Invalid date format: {exc}")
        return

    registry.update_state(
        source,
        JobState.WAITING_FOR_AUTH,
        f"Connecting to Chrome at {cdp_url}…",
    )

    try:
        # Imports live inside the try so a broken Playwright install fails
        # the job instead of leaving it stuck in PENDING forever.
        import time

        from playwright.sync_api import sync_playwright

        from ..core.importer import ImportError_, import_file
        from ..db import get_session_factory

        with sync_playwright() as pw:
            # Fail fast if CDP Chrome is not running.
            try:
                browser = pw.chromium.connect_over_cdp(cdp_url)
            except Exception as exc:  # noqa: BLE001
                _fail(connect_failure_message(cdp_url, exc, WISE_TRANSACTIONS_URL))
                return

            if not browser.contexts:
                _fail(no_contexts_message(cdp_url))
                return

            context = browser.contexts[0]
            page = context.new_page()
            page.goto(WISE_TRANSACTIONS_URL, wait_until="load")

            registry.update_state(
                source,
                JobState.WAITING_FOR_AUTH,
                "Waiting for Wise login (check the Chrome window)…",
            )

            # Poll for the logged-in page: the SSR HTML embeds the profile id
            # only once the session is authenticated.
            profile_id = None
            deadline = time.monotonic() + _AUTH_TIMEOUT_MS / 1_000
            while time.monotonic() < deadline:
                try:
                    profile_id = extract_profile_id(page.content())
                except Exception:  # noqa: BLE001
                    profile_id = None
                if profile_id:
                    break
                time.sleep(_AUTH_POLL_SECONDS)
            if not profile_id:
                _fail("Login timeout — please retry and sign in to Wise within 5 minutes.")
                return

            logger.info("wise_authenticated", profile_id=profile_id)
            registry.update_state(
                source, JobState.DOWNLOADING, "Downloading CSV export from Wise…"
            )

            try:
                resp = page.request.post(
                    WISE_EXPORT_URL.format(profile_id=profile_id),
                    data={"size": _EXPORT_MAX_ROWS, "since": since, "until": until},
                    headers={
                        "x-access-token": WISE_ACCESS_TOKEN,
                        "accept": "text/csv;charset=UTF-8",
                    },
                )
                if not resp.ok:
                    _fail(f"Wise export failed with status {resp.status}: {resp.text()[:300]}")
                    return
                csv_bytes = resp.body()
            except Exception as exc:  # noqa: BLE001
                _fail(f"Download failed: {exc}")
                return
            finally:
                # Close the tab we opened, then detach. close() on a
                # CDP-connected browser only disconnects — the user's real
                # Chrome stays open.
                try:
                    page.close()
                    page = None
                except Exception:  # noqa: BLE001
                    pass
                try:
                    browser.close()
                    browser = None
                except Exception:  # noqa: BLE001
                    pass

            if not csv_bytes.strip() or csv_bytes.strip().count(b"\n") == 0:
                _fail("Wise export returned no transactions for this date range.")
                return

            settings.statements_dir.mkdir(parents=True, exist_ok=True)
            filename = f"wise-{from_date}-{to_date}.csv"
            dest = settings.statements_dir / filename
            dest.write_bytes(csv_bytes)
            logger.info("wise_file_saved", path=str(dest))

            # --- Import phase ---
            registry.update_state(source, JobState.IMPORTING, "Importing Wise CSV…")

            session_factory = get_session_factory()
            with session_factory() as db:
                try:
                    summary = import_file(
                        db,
                        csv_bytes,
                        filename,
                        settings.statements_dir,
                        fmt="wise",
                    )
                except ImportError_ as exc:
                    _fail(f"Import failed: {exc}")
                    return
                # Bookmark uses DD-MM-YYYY like the other sources.
                to_ddmmyyyy = datetime.strptime(to_date, "%Y-%m-%d").strftime("%d-%m-%Y")
                _update_download_state(db, source, None, to_ddmmyyyy)

            s = summary.as_dict()
            registry.set_summary(
                source,
                {
                    "files": [s["source_file"]],
                    "new": s["new"],
                    "duplicates": s["duplicates"],
                    "categorized": s["categorized"],
                    "uncategorized": s["uncategorized"],
                    "failed_files": [],
                },
            )
            registry.update_state(
                source,
                JobState.DONE,
                f"Done — {s['new']} new transaction(s) imported.",
            )

    except Exception as exc:  # noqa: BLE001
        _fail(f"Unexpected error: {exc}")
        logger.exception("wise_job_unexpected_error", error=str(exc))
