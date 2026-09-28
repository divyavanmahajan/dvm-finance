"""SEB download worker — attaches to the user's real Chrome over CDP.

Protocol (see protocol/seb.se-protocol.md): after BankID login the
apps.seb.se APIs are plain cookie-authenticated. The account list comes from
a JSON endpoint; each account's transactions are exported as
semicolon-separated CSV via a form-encoded POST. The export has no date
filter — it returns the account's recent history and the importer dedups.
"""

from __future__ import annotations

import json
import uuid
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

SEB_ACCOUNTS_PAGE_URL = "https://apps.seb.se/cps/payments/accounts"
SEB_ACCOUNTS_API = "https://apps.seb.se/ssc/payments/accounts/api/accounts"
SEB_CSV_URL = "https://apps.seb.se/ssc/payments/accounts/api/accounts/{account_id}/csv"

_AUTH_TIMEOUT_MS = 5 * 60 * 1_000  # 5 minutes (BankID)
_AUTH_POLL_SECONDS = 3


def csv_export_payload(account: dict) -> dict:
    """Build the /csv form payload from an accounts-list entry."""
    owner = account.get("primary_account_owner") or {}
    return {
        "requestId": str(uuid.uuid4()),
        "accountId": account["id"],
        "bban": account.get("bban"),
        "isActive": True,
        "currencyCode": account.get("currency_code"),
        "accountName": account.get("custom_name"),
        "customerId": owner.get("personal_identity_number"),
        "searchFilter": {"filters": None},
    }


# ---------------------------------------------------------------------------
# Job runner (executed in a worker thread)
# ---------------------------------------------------------------------------


def run_seb_job(
    registry: JobRegistry,
    settings: Settings,
    cdp_url: str = DEFAULT_CDP_URL,
) -> None:
    """Worker function — runs in a dedicated thread.

    Updates registry state:
    pending → waiting-for-auth → downloading → importing → done/failed.
    """
    source = "seb"
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
                _fail(connect_failure_message(cdp_url, exc, SEB_ACCOUNTS_PAGE_URL))
                return

            if not browser.contexts:
                _fail(no_contexts_message(cdp_url))
                return

            context = browser.contexts[0]
            page = context.new_page()
            page.goto(SEB_ACCOUNTS_PAGE_URL, wait_until="load")

            registry.update_state(
                source,
                JobState.WAITING_FOR_AUTH,
                "Waiting for SEB BankID login (check the Chrome window)…",
            )

            # Poll the accounts API — it returns account data only once the
            # session is authenticated (login redirects to id.seb.se).
            accounts: list[dict] = []
            deadline = time.monotonic() + _AUTH_TIMEOUT_MS / 1_000
            while time.monotonic() < deadline:
                try:
                    # The API 415s without an explicit JSON content type,
                    # even on GET.
                    resp = page.request.get(
                        SEB_ACCOUNTS_API,
                        headers={
                            "accept": "application/json",
                            "content-type": "application/json",
                        },
                    )
                    if resp.ok:
                        data = resp.json()
                        accounts = (data.get("data") or {}).get("active_accounts") or []
                        if accounts:
                            break
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(_AUTH_POLL_SECONDS)
            if not accounts:
                _fail("Login timeout — please retry and complete BankID login within 5 minutes.")
                return

            logger.info("seb_authenticated", accounts=len(accounts))
            registry.update_state(
                source,
                JobState.DOWNLOADING,
                f"Downloading CSV for {len(accounts)} account(s) from SEB…",
            )

            today = datetime.now().date().isoformat()
            settings.statements_dir.mkdir(parents=True, exist_ok=True)
            saved: list = []
            try:
                for account in accounts:
                    payload = csv_export_payload(account)
                    resp = page.request.post(
                        SEB_CSV_URL.format(account_id=account["id"]),
                        form={"data": json.dumps(payload), "lang": "en"},
                    )
                    if not resp.ok:
                        _fail(
                            f"SEB export failed for account {account.get('bban')} "
                            f"with status {resp.status}: {resp.text()[:300]}"
                        )
                        return
                    body = resp.body()
                    # Header-only responses mean no transactions for this account.
                    if body.strip().count(b"\n") == 0:
                        logger.info("seb_account_empty", bban=account.get("bban"))
                        continue
                    dest = settings.statements_dir / f"seb-{account.get('bban')}-{today}.csv"
                    dest.write_bytes(body)
                    logger.info("seb_file_saved", path=str(dest))
                    saved.append(dest)
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

            if not saved:
                _fail("SEB returned no transactions for any account.")
                return

            # --- Import phase ---
            registry.update_state(
                source, JobState.IMPORTING, f"Importing {len(saved)} file(s)…"
            )

            summaries = []
            failed_files = []
            session_factory = get_session_factory()
            with session_factory() as db:
                for path in saved:
                    try:
                        summary = import_file(
                            db,
                            path.read_bytes(),
                            path.name,
                            settings.statements_dir,
                            fmt="seb",
                        )
                        summaries.append(summary.as_dict())
                        logger.info("seb_file_imported", file=path.name, new=summary.new)
                    except ImportError_ as exc:
                        logger.warning("seb_import_failed", file=path.name, error=str(exc))
                        failed_files.append(f"{path.name}: {exc}")

                # Bookmark uses DD-MM-YYYY like the other sources.
                _update_download_state(
                    db, source, None, datetime.now().date().strftime("%d-%m-%Y")
                )

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
                f"Done — {aggregate['new']} new transaction(s) imported "
                f"from {len(saved)} file(s).",
            )

    except Exception as exc:  # noqa: BLE001
        _fail(f"Unexpected error: {exc}")
        logger.exception("seb_job_unexpected_error", error=str(exc))
