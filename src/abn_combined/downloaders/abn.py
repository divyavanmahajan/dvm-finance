"""ABN AMRO download worker — ported from abn-download/abn_download.py.

Protocol code is kept diff-able against the source; only CLI-specific parts
(argparse, prompts, upload_utils) are replaced by job-registry callbacks and
the import pipeline.
"""

from __future__ import annotations

import base64
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.jobs import JobRegistry, JobState
from ..logging_config import get_logger
from .browser import (
    DEFAULT_CDP_URL,
    connect_failure_message,
    missing_playwright_message,
    no_contexts_message,
)

if TYPE_CHECKING:
    from ..settings import Settings

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Protocol constants (ported verbatim)
# ---------------------------------------------------------------------------

ABN_TRANSACTIONS_URL = (
    "https://www.abnamro.nl/my-abnamro/payments/download-overviews/#/transactions"
)
ABN_GENERATIONS_API = "https://www.abnamro.nl/mutationreporting/generations/v1"
ABN_ACCOUNT_BALANCES_API = (
    "https://www.abnamro.nl/my-abnamro/apis/account-balances/v3/"
)

# The product groups for the account-balances API. These groups come verbatim
# from the request that the ABN AMRO web app makes. The same account can occur
# in more than one group. The caller removes the duplicates.
ABN_PRODUCT_GROUPS = (
    "PAYMENT_ACCOUNTS,SAVINGS_ACCOUNTS,INVESTMENTS,CREDITS_ACBS,"
    "CREDITS_BSK_INTERBANK,CREDITS_MAHUKO_REVOLVING,FISCAL_CAPITAL_SOLUTIONS,"
    "FISCAL_CAPITAL_SOLUTIONS_PRODUCTS,INSURANCES,DEPOSITS,CONSUMER_LOANS,"
    "SETTLEMENTACCOUNTS_FOR_SAVINGS,CREDIT_CARDS_CORPORATE,CREDIT_CARDS_RETAIL,"
    "GUARANTEES,INSURANCES_INDEMNITY,INSURANCES_LIFE,MORTGAGE,OTHER_SERVICES,"
    "PAYMENT_PACKAGES,PAYMENT_SERVICES,VARIABLE_SAVINGS_TOR_BONUS,"
    "VARIABLE_SAVINGS_TOR_FLAT"
)

_AUTH_TIMEOUT_MS = 5 * 60 * 1_000  # 5 minutes


# ---------------------------------------------------------------------------
# Ported pure functions (no CLI deps)
# ---------------------------------------------------------------------------


def dismiss_cookie_banner(page, timeout_ms: int = 5_000) -> None:
    """Dismiss the ABN AMRO cookie banner if it appears."""
    try:
        page.get_by_role("button", name="I do not accept").click(timeout=timeout_ms)
        logger.info("abn_cookie_banner_dismissed")
    except Exception:  # noqa: BLE001
        pass


def _wait_for_app_login_redirect(
    page,
    target_url: str = ABN_TRANSACTIONS_URL,
    timeout_ms: int = _AUTH_TIMEOUT_MS,
) -> None:
    """Wait for the user to approve login in the ABN AMRO app.

    Raises ``TimeoutError`` (via Playwright) on timeout.
    """
    if page.url == target_url:
        logger.info("abn_already_authenticated")
        return
    page.wait_for_url(target_url, timeout=timeout_ms)
    logger.info("abn_authenticated")


def extract_account_numbers(response_data: dict) -> list[str]:
    """Get the account numbers for the generations API from a balances response.

    The account-balances response has one entry for each contract. The same
    account occurs one time for each of its product groups. Other contracts,
    such as a debit card or an access agreement, have no ``accountNumber``.
    An entry is an account only if it has an ``accountNumber``. The
    ``contractNumber`` of the entry is the account number with a zero prefix,
    for example ``"0123456789"`` for the account number ``"123456789"``.

    The function returns the numbers in first-seen order. It removes the
    duplicates.
    """
    numbers: list[str] = []
    seen: set[str] = set()
    for item in response_data.get("contractList", []):
        contract = (item or {}).get("contract") or {}
        if not contract.get("accountNumber"):
            continue
        contract_number = str(contract.get("contractNumber") or "").strip()
        number = contract_number.lstrip("0")
        if not number or number in seen:
            continue
        seen.add(number)
        numbers.append(number)
    return numbers


def fetch_account_numbers(page) -> list[str]:
    """Read the account-balances API and return the account numbers.

    The function uses the request context of the authenticated page. The page
    sends the ABN AMRO session cookies. The app does not store an account
    number.
    """
    url = f"{ABN_ACCOUNT_BALANCES_API}?productGroups={ABN_PRODUCT_GROUPS}"
    logger.info("abn_api_get", url=ABN_ACCOUNT_BALANCES_API)
    response = page.request.get(url, headers={"accept": "application/json"})
    if not response.ok:
        raise Exception(
            f"ABN account-balances request failed with status {response.status}: "
            f"{response.text()}"
        )
    numbers = extract_account_numbers(response.json())
    logger.info("abn_accounts_discovered", count=len(numbers))
    return numbers


def download_transactions(
    page,
    account_numbers: list[str],
    from_date: str,
    to_date: str,
    from_last_download_date: bool = False,
) -> dict:
    """POST to ABN AMRO generations API; return the response JSON.

    Args:
        page: Authenticated Playwright page (session cookies in use).
        account_numbers: List of account numbers to download.
        from_date: Start date in DD-MM-YYYY format.
        to_date: End date in DD-MM-YYYY format.
        from_last_download_date: Whether to use the bank's own "last download" bookmark.
    """
    payload = {
        "generations": {
            "accountNumbers": account_numbers,
            "fromLastDownloadDate": from_last_download_date,
            "fromDate": from_date,
            "toDate": to_date,
            "format": "MT940",
        }
    }
    logger.info("abn_api_post", url=ABN_GENERATIONS_API)
    response = page.request.post(ABN_GENERATIONS_API, data=payload)
    if response.ok:
        return response.json()
    raise Exception(
        f"ABN API request failed with status {response.status}: {response.text()}"
    )


def decode_and_save_reports(
    response_data: dict,
    statements_dir: Path,
) -> list[Path]:
    """Decode base64 MT940 payloads from the API response and save them.

    Returns a list of saved :class:`~pathlib.Path` objects.
    """
    statements_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for report in response_data.get("reports", []):
        filename = report.get("fileName")
        file_bytes_b64 = report.get("fileBytes")
        if filename and file_bytes_b64:
            content = base64.b64decode(file_bytes_b64)
            dest = statements_dir / filename
            dest.write_bytes(content)
            logger.info("abn_file_saved", path=str(dest))
            saved.append(dest)
        else:
            logger.warning("abn_report_missing_fields", report_keys=list(report.keys()))
    return saved


def get_default_date_range(last_range_end: date | None) -> tuple[str, str]:
    """Return (from_date, to_date) in DD-MM-YYYY format.

    *from_date* defaults to the day after the last successful download end, or 30 days ago.
    *to_date* is today. Never later than *to_date*: after a download that
    already covered today, the range would otherwise invert (tomorrow → today),
    so it is clamped to today (re-downloading today is safe — imports dedup).
    """
    today = datetime.now().date()
    if last_range_end:
        from_dt = min(last_range_end + timedelta(days=1), today)
    else:
        from_dt = today - timedelta(days=30)
    return from_dt.strftime("%d-%m-%Y"), today.strftime("%d-%m-%Y")


# ---------------------------------------------------------------------------
# Job runner (executed in a worker thread)
# ---------------------------------------------------------------------------


def run_abn_job(
    registry: JobRegistry,
    settings: Settings,
    account_numbers: list[str] | None,
    from_date: str,
    to_date: str,
    from_last_download_date: bool = False,
    cdp_url: str = DEFAULT_CDP_URL,
) -> None:
    """Worker function — runs in a dedicated thread.

    Updates registry state as the job progresses:
    pending → waiting-for-auth → downloading → importing → done/failed.

    If *account_numbers* is ``None`` or empty, the job reads the accounts from
    the ABN AMRO account-balances API after the user authenticates the session.
    The app does not store an account number.

    Connects to the user's real Chrome over CDP (same approach as the PayPal
    downloader) instead of launching a Playwright-managed browser — so this
    never needs `playwright install`, and the persistent Chrome profile keeps
    ABN AMRO session cookies across runs. On CDP connection failure, fails
    immediately with the exact Chrome launch command.
    """
    source = "abn"
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
        from playwright.sync_api import TimeoutError as PWTimeout
        from playwright.sync_api import sync_playwright

        from ..core.importer import ImportError_, import_file
        from ..db import get_session_factory

        with sync_playwright() as pw:
            # Fail fast if CDP Chrome is not running.
            try:
                browser = pw.chromium.connect_over_cdp(cdp_url)
            except Exception as exc:  # noqa: BLE001
                _fail(connect_failure_message(cdp_url, exc, ABN_TRANSACTIONS_URL))
                return

            if not browser.contexts:
                _fail(no_contexts_message(cdp_url))
                return

            context = browser.contexts[0]
            page = context.new_page()
            page.goto(ABN_TRANSACTIONS_URL, wait_until="load")
            dismiss_cookie_banner(page)

            registry.update_state(
                source,
                JobState.WAITING_FOR_AUTH,
                "Waiting for ABN AMRO app authentication (check the Chrome window)…",
            )

            try:
                _wait_for_app_login_redirect(page)
            except PWTimeout:
                _fail("Authentication timeout. Please retry and complete login within 5 minutes.")
                return
            except Exception as exc:  # noqa: BLE001
                _fail(f"Authentication error: {exc}")
                return

            if not account_numbers:
                registry.update_state(
                    source,
                    JobState.DOWNLOADING,
                    "Listing ABN AMRO accounts…",
                )
                try:
                    account_numbers = fetch_account_numbers(page)
                except Exception as exc:  # noqa: BLE001
                    _fail(f"Could not list ABN AMRO accounts: {exc}")
                    return
                if not account_numbers:
                    _fail(
                        "The app found no ABN AMRO accounts for this login. "
                        "There is nothing to download."
                    )
                    return

            registry.update_state(
                source,
                JobState.DOWNLOADING,
                f"Found {len(account_numbers)} account(s); "
                "downloading MT940 files from ABN AMRO…",
            )

            try:
                response_data = download_transactions(
                    page, account_numbers, from_date, to_date, from_last_download_date
                )
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

            saved_files = decode_and_save_reports(response_data, settings.statements_dir)
            if not saved_files:
                _fail("No MT940 files returned by the ABN AMRO API.")
                return

            # --- Import phase ---
            registry.update_state(source, JobState.IMPORTING, f"Importing {len(saved_files)} file(s)…")

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
                            settings.statements_dir,
                            fmt="auto",
                        )
                        summaries.append(summary.as_dict())
                        logger.info("abn_file_imported", file=path.name, new=summary.new)
                    except ImportError_ as exc:
                        logger.warning("abn_import_failed", file=path.name, error=str(exc))
                        failed_files.append(f"{path.name}: {exc}")

                # Update download_state bookmark.
                _update_download_state(db, "abn", None, to_date)

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
        if isinstance(exc, ModuleNotFoundError) and exc.name == "playwright":
            _fail(missing_playwright_message())
            logger.warning("abn_job_playwright_missing")
            return
        _fail(f"Unexpected error: {exc}")
        logger.exception("abn_job_unexpected_error", error=str(exc))


def _update_download_state(db, source: str, account: str | None, to_date_str: str) -> None:
    """Upsert the DownloadState bookmark for *source/account*."""
    from datetime import datetime as dt

    from sqlalchemy import select

    from ..core.models import DownloadState

    # Parse to_date_str (DD-MM-YYYY)
    try:
        end = dt.strptime(to_date_str, "%d-%m-%Y").date()
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
    row.last_success_at = dt.utcnow()
    row.last_range_end = end
    db.commit()
