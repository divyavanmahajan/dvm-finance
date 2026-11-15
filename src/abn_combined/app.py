"""FastAPI application factory."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__
from .db import configure_engine
from .logging_config import configure_logging, get_logger
from .settings import Settings

logger = get_logger(__name__)

_PACKAGE_DIR = Path(__file__).parent
_TEMPLATES_DIR = _PACKAGE_DIR / "web" / "templates"
_STATIC_DIR = _PACKAGE_DIR / "web" / "static"

# Nav tabs: (route path, label)
NAV_TABS = [
    ("/", "Transactions"),
    ("/trends", "Trends"),
    ("/rules", "Rules"),
    ("/tags", "Tags"),
    ("/budgets", "Budgets"),
    ("/cash-flow", "Cash Flow"),
    ("/download", "Download"),
    ("/upload", "Upload"),
    ("/manual", "Cash"),
    ("/snapshots", "Snapshots"),
    ("/help", "Help"),
]

def _css_id(s: str) -> str:
    """Make an arbitrary string safe for use as a CSS ID selector component.

    HTML ids may contain any character; CSS selectors cannot — ``:`` triggers
    pseudo-class parsing, ``.`` triggers class parsing, etc.  Replace every
    character that is not alphanumeric, hyphen, or underscore with ``_``.
    Used in templates via the ``css_id`` filter so ``hx-target`` selectors
    always resolve correctly even when transaction IDs come from PayPal
    (``pp:buyer_…``) or ABN (``…_2000.0_…``).
    """
    return re.sub(r"[^a-zA-Z0-9_-]", "_", str(s))


def _static_url(path: str) -> str:
    """Return the URL of a static file with its change time as a version.

    The static files have no Cache-Control header, so a browser can keep an
    old copy for days. A new version in the URL makes it fetch the new file.
    """
    try:
        version = int((_STATIC_DIR / path).stat().st_mtime)
    except OSError:
        return f"/static/{path}"
    return f"/static/{path}?v={version}"


templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["static_url"] = _static_url
templates.env.globals["nav_tabs"] = NAV_TABS
templates.env.globals["app_version"] = __version__
templates.env.filters["css_id"] = _css_id


def create_app(settings: Settings) -> FastAPI:
    """Build the FastAPI application for the given settings."""
    configure_logging()
    settings.ensure_data_dir()
    configure_engine(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        from .core.restructure import (
            migrate_rule_field_targets,
            rewrite_sepa_structured_descriptions,
        )
        from .db import get_session_factory
        from .migrations import upgrade_to_head

        upgrade_to_head(settings)
        # One-time pass: the rules read the stored structured description, so a
        # row from before the canonical SEPA keys needs a reparse. The pass
        # matches no row after its first run.
        db = get_session_factory()()
        try:
            rewrite_sepa_structured_descriptions(db)
            # A rule names a structured key by its field target. The rename of a
            # key must carry each rule with it, or the rule would match nothing.
            migrate_rule_field_targets(db)
        finally:
            db.close()
        logger.info("app_started", data_dir=str(settings.data_dir))
        yield

    app = FastAPI(title="dvm-finance", lifespan=lifespan)
    app.state.settings = settings

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "data_dir": str(settings.data_dir)}

    # Real routers claim their paths first; nav tabs without a router get a placeholder.
    _register_api_routers(app)
    claimed = {getattr(r, "path", None) for r in app.routes}

    def _placeholder(title: str):
        def page(request: Request) -> HTMLResponse:
            return templates.TemplateResponse(
                request,
                "placeholder.html",
                {"active_path": request.url.path, "title": title},
            )

        return page

    for path, label in NAV_TABS:
        if path in claimed:
            continue
        app.add_api_route(
            path,
            _placeholder(label),
            methods=["GET"],
            response_class=HTMLResponse,
            include_in_schema=False,
        )

    return app


# Router modules under abn_combined.api; each exposes `router`. Modules that
# don't exist yet are skipped so partial builds still boot.
API_ROUTER_MODULES = [
    "upload",
    "transactions",
    "rules",
    "trends",
    "tags",
    "budgets",
    "manual",
    "cash_flow",
    "downloads",
    "snapshots",
    "merge",
    "help",
]


def _register_api_routers(app: FastAPI) -> None:
    """Register API routers. Guarded so partial builds still boot."""
    import importlib

    for mod_name in API_ROUTER_MODULES:
        try:
            module = importlib.import_module(f".api.{mod_name}", __package__)
        except ImportError:  # pragma: no cover - module not built yet
            continue
        app.include_router(module.router)
