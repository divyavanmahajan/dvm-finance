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


def _templates(request: Request):
    from ..app import templates

    return templates


# ---------------------------------------------------------------------------
# Date-default helpers
# ---------------------------------------------------------------------------


def _abn_default_dates(db: Session) -> tuple[str, str]:
    """Return (from_date, to_date) in YYYY-MM-DD for the ABN form."""
    from sqlalchemy import select

    from ..core.models import DownloadState
    from ..downloaders.abn import get_default_date_range

    stmt = select(DownloadState).where(
        DownloadState.source == "abn",
        DownloadState.account.is_(None),
    )
    row = db.execute(stmt).scalar_one_or_none()
    last_end = row.last_range_end if row else None
    from_abn, to_abn = get_default_date_range(last_end)
    return _abn_to_iso(from_abn), _abn_to_iso(to_abn)


def _abn_to_iso(d: str) -> str:
    """DD-MM-YYYY (ABN API format) → YYYY-MM-DD (form format)."""
    from datetime import datetime

    return datetime.strptime(d, "%d-%m-%Y").strftime("%Y-%m-%d")


def _iso_to_abn(d: str) -> str:
    """YYYY-MM-DD (form format) → DD-MM-YYYY (ABN API format).

    Raises HTTPException(400) on malformed input.
    """
    from datetime import datetime

    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid date {d!r}; expected YYYY-MM-DD."
        ) from exc


def _iso_default_dates(db: Session, source: str, default_days: int = 180) -> tuple[str, str]:
    """Return (from_date, to_date) in YYYY-MM-DD for *source*'s form.

    *from_date* defaults to the day after the last successful download end,
    or *default_days* ago — clamped to today so the range never inverts after
    a download that already covered today (re-downloading today is safe —
    imports dedup).
    """
    from sqlalchemy import select

    from ..core.models import DownloadState

    stmt = select(DownloadState).where(
        DownloadState.source == source,
        DownloadState.account.is_(None),
    )
    row = db.execute(stmt).scalar_one_or_none()

    today = date.today()
    if row and row.last_range_end:
        from_dt = min(row.last_range_end + timedelta(days=1), today)
    else:
        from_dt = today - timedelta(days=default_days)

    return from_dt.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")


def _paypal_default_dates(db: Session) -> tuple[str, str]:
    return _iso_default_dates(db, "paypal")


# ---------------------------------------------------------------------------
# Download page
# ---------------------------------------------------------------------------


@router.get("/download", response_class=HTMLResponse, include_in_schema=False)
def download_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    registry = get_registry()

    abn_from, abn_to = _abn_default_dates(db)
    pp_from, pp_to = _paypal_default_dates(db)
    wise_from, wise_to = _iso_default_dates(db, "wise")

    from ..downloaders.browser import DEFAULT_CDP_URL, chrome_launch_command

    return _templates(request).TemplateResponse(
        request,
        "download.html",
        {
            "active_path": "/download",
            "title": "Download",
            "abn_job": registry.get("abn"),
            "paypal_job": registry.get("paypal"),
            "wise_job": registry.get("wise"),
            "seb_job": registry.get("seb"),
            "abn_from": abn_from,
            "abn_to": abn_to,
            "pp_from": pp_from,
            "pp_to": pp_to,
            "wise_from": wise_from,
            "wise_to": wise_to,
            "chrome_launch_command": chrome_launch_command(),
            "default_cdp_url": DEFAULT_CDP_URL,
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
    cdp_url: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Start an ABN AMRO download job in a background thread."""
    registry = get_registry()

    if registry.is_running("abn"):
        raise HTTPException(status_code=409, detail="ABN AMRO download already running.")

    # Resolve dates (fall back to defaults if blank), then convert the
    # form's YYYY-MM-DD to the DD-MM-YYYY the ABN API expects.
    if not from_date or not to_date:
        from_date, to_date = _abn_default_dates(db)
    from_date, to_date = _iso_to_abn(from_date), _iso_to_abn(to_date)

    from ..downloaders.browser import DEFAULT_CDP_URL

    if not cdp_url:
        cdp_url = DEFAULT_CDP_URL

    settings = request.app.state.settings

    from ..downloaders.abn import _DEFAULT_ACCOUNTS, run_abn_job

    registry.create("abn")

    t = threading.Thread(
        target=run_abn_job,
        args=(registry, settings, _DEFAULT_ACCOUNTS, from_date, to_date),
        kwargs={"cdp_url": cdp_url},
        daemon=True,
        name="abn-download",
    )
    t.start()

    logger.info("abn_job_started", from_date=from_date, to_date=to_date)
    return _status_partial(request, "abn")


@router.post("/api/download/wise", response_class=HTMLResponse)
def start_wise_download(
    request: Request,
    from_date: Annotated[str, Form()] = "",
    to_date: Annotated[str, Form()] = "",
    cdp_url: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Start a Wise download job in a background thread."""
    registry = get_registry()

    if registry.is_running("wise"):
        raise HTTPException(status_code=409, detail="Wise download already running.")

    if not from_date or not to_date:
        from_date, to_date = _iso_default_dates(db, "wise")

    from ..downloaders.browser import DEFAULT_CDP_URL
    from ..downloaders.wise import run_wise_job

    if not cdp_url:
        cdp_url = DEFAULT_CDP_URL

    settings = request.app.state.settings
    registry.create("wise")

    t = threading.Thread(
        target=run_wise_job,
        args=(registry, settings, from_date, to_date),
        kwargs={"cdp_url": cdp_url},
        daemon=True,
        name="wise-download",
    )
    t.start()

    logger.info("wise_job_started", from_date=from_date, to_date=to_date)
    return _status_partial(request, "wise")


@router.post("/api/download/seb", response_class=HTMLResponse)
def start_seb_download(
    request: Request,
    cdp_url: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Start a SEB download job in a background thread.

    No date range — the SEB export returns the account's recent history and
    the importer skips duplicates.
    """
    registry = get_registry()

    if registry.is_running("seb"):
        raise HTTPException(status_code=409, detail="SEB download already running.")

    from ..downloaders.browser import DEFAULT_CDP_URL
    from ..downloaders.seb import run_seb_job

    if not cdp_url:
        cdp_url = DEFAULT_CDP_URL

    settings = request.app.state.settings
    registry.create("seb")

    t = threading.Thread(
        target=run_seb_job,
        args=(registry, settings),
        kwargs={"cdp_url": cdp_url},
        daemon=True,
        name="seb-download",
    )
    t.start()

    logger.info("seb_job_started")
    return _status_partial(request, "seb")


@router.post("/api/download/launch-chrome", response_class=HTMLResponse)
def launch_chrome(
    request: Request,
    cdp_url: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Launch real Chrome with remote debugging, shared by every source —
    each download job opens its own tab, so no start URL is needed."""
    from ..downloaders.browser import DEFAULT_CDP_URL, launch_chrome_debug

    try:
        launch_chrome_debug(cdp_url or DEFAULT_CDP_URL)
    except FileNotFoundError as exc:
        logger.warning("chrome_launch_failed", error=str(exc))
        return _templates(request).TemplateResponse(
            request, "_chrome_status.html", {"error": str(exc)}
        )
    logger.info("chrome_launched", cdp_url=cdp_url or DEFAULT_CDP_URL)
    return _templates(request).TemplateResponse(
        request, "_chrome_status.html", {"error": None}
    )


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
    if source not in ("abn", "paypal", "wise", "seb"):
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
        # oob lets the partial refresh the card's submit button out-of-band;
        # full-page renders include the partial without it.
        {"source": source, "job": job, "oob": True},
    )
