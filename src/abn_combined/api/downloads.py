"""Downloads page and background-job API endpoints."""

from __future__ import annotations

import threading
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..core.jobs import get_registry
from ..db import get_db
from ..logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Playwright availability check (NFR5)
# ---------------------------------------------------------------------------

def _playwright_available() -> bool:
    """Return True when Playwright is installed *and* Chromium browsers are present."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401

        with sync_playwright() as pw:
            # executable_path raises or returns empty string when missing.
            path = pw.chromium.executable_path
            return bool(path)
    except Exception:  # noqa: BLE001
        return False


def _templates(request: Request):
    from ..app import templates

    return templates


# ---------------------------------------------------------------------------
# Date-default helpers
# ---------------------------------------------------------------------------


def _abn_default_dates(db: Session) -> tuple[str, str]:
    """Return (from_date, to_date) in DD-MM-YYYY for the ABN form."""
    from sqlalchemy import select

    from ..core.models import DownloadState
    from ..downloaders.abn import get_default_date_range

    stmt = select(DownloadState).where(
        DownloadState.source == "abn",
        DownloadState.account.is_(None),
    )
    row = db.execute(stmt).scalar_one_or_none()
    last_end = row.last_range_end if row else None
    return get_default_date_range(last_end)


def _paypal_default_dates(db: Session) -> tuple[str, str]:
    """Return (from_date, to_date) in YYYY-MM-DD for the PayPal form."""
    from sqlalchemy import select

    from ..core.models import DownloadState

    stmt = select(DownloadState).where(
        DownloadState.source == "paypal",
        DownloadState.account.is_(None),
    )
    row = db.execute(stmt).scalar_one_or_none()

    today = date.today()
    if row and row.last_range_end:
        from_dt = row.last_range_end + timedelta(days=1)
    else:
        from_dt = today - timedelta(days=180)

    return from_dt.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Download page
# ---------------------------------------------------------------------------


@router.get("/download", response_class=HTMLResponse, include_in_schema=False)
def download_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    registry = get_registry()
    abn_job = registry.get("abn")
    paypal_job = registry.get("paypal")

    playwright_ok = _playwright_available()
    abn_from, abn_to = _abn_default_dates(db)
    pp_from, pp_to = _paypal_default_dates(db)

    from ..downloaders.paypal import CHROME_LAUNCH_COMMAND

    return _templates(request).TemplateResponse(
        request,
        "download.html",
        {
            "active_path": "/download",
            "title": "Download",
            "playwright_available": playwright_ok,
            "abn_job": abn_job,
            "paypal_job": paypal_job,
            "abn_from": abn_from,
            "abn_to": abn_to,
            "pp_from": pp_from,
            "pp_to": pp_to,
            "chrome_launch_command": CHROME_LAUNCH_COMMAND,
        },
    )


# ---------------------------------------------------------------------------
# Start-job endpoints
# ---------------------------------------------------------------------------


@router.post("/api/download/abn", response_class=HTMLResponse)
def start_abn_download(
    request: Request,
    from_date: Annotated[str, Form()] = "",
    to_date: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Start an ABN AMRO download job in a background thread."""
    registry = get_registry()

    if registry.is_running("abn"):
        raise HTTPException(status_code=409, detail="ABN AMRO download already running.")

    if not _playwright_available():
        raise HTTPException(
            status_code=503,
            detail="Playwright/Chromium not available. Run: playwright install chromium",
        )

    # Resolve dates (fall back to defaults if blank).
    if not from_date or not to_date:
        from_date, to_date = _abn_default_dates(db)

    settings = request.app.state.settings

    from ..downloaders.abn import _DEFAULT_ACCOUNTS, run_abn_job

    registry.create("abn")

    t = threading.Thread(
        target=run_abn_job,
        args=(registry, settings, _DEFAULT_ACCOUNTS, from_date, to_date),
        daemon=True,
        name="abn-download",
    )
    t.start()

    logger.info("abn_job_started", from_date=from_date, to_date=to_date)
    return _status_partial(request, "abn")


@router.post("/api/download/paypal", response_class=HTMLResponse)
def start_paypal_download(
    request: Request,
    from_date: Annotated[str, Form()] = "",
    to_date: Annotated[str, Form()] = "",
    cdp_url: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Start a PayPal download job in a background thread."""
    registry = get_registry()

    if registry.is_running("paypal"):
        raise HTTPException(status_code=409, detail="PayPal download already running.")

    if not from_date or not to_date:
        from_date, to_date = _paypal_default_dates(db)

    from ..downloaders.paypal import DEFAULT_CDP_URL, run_paypal_job

    if not cdp_url:
        cdp_url = DEFAULT_CDP_URL

    settings = request.app.state.settings
    registry.create("paypal")

    t = threading.Thread(
        target=run_paypal_job,
        args=(registry, settings, from_date, to_date, cdp_url),
        daemon=True,
        name="paypal-download",
    )
    t.start()

    logger.info("paypal_job_started", from_date=from_date, to_date=to_date)
    return _status_partial(request, "paypal")


# ---------------------------------------------------------------------------
# Status polling endpoint
# ---------------------------------------------------------------------------


@router.get("/api/download/{source}/status", response_class=HTMLResponse)
def download_status(source: str, request: Request) -> HTMLResponse:
    """Return the htmx status partial for *source*.  Polled every ~2 s."""
    if source not in ("abn", "paypal"):
        raise HTTPException(status_code=404, detail=f"Unknown source: {source}")
    return _status_partial(request, source)


# ---------------------------------------------------------------------------
# Internal partial helper
# ---------------------------------------------------------------------------


def _status_partial(request: Request, source: str) -> HTMLResponse:
    registry = get_registry()
    job = registry.get(source)
    return _templates(request).TemplateResponse(
        request,
        "_download_status.html",
        {"source": source, "job": job},
    )
