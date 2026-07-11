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
    ("/snapshots", "Snapshots"),
]

def _css_id(s: str) -> str:
    """Make an arbitrary string safe for use as a CSS ID selector component.

    HTML ids may contain any character; CSS selectors cannot — ``:`` triggers
    pseudo-class parsing, ``.`` triggers class parsing, etc.  Replace every
    character that is not alphanumeric, hyphen, or underscore with ``_``.
    Used in templates via the ``css_id`` filter so ``hx-target`` selectors
    always resolve correctly even when transaction IDs come from PayPal
    (``pp:paypaleu_…``) or ABN (``…_2000.0_…``).
    """
    return re.sub(r"[^a-zA-Z0-9_-]", "_", str(s))


templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["nav_tabs"] = NAV_TABS
templates.env.filters["css_id"] = _css_id


def create_app(settings: Settings) -> FastAPI:
    """Build the FastAPI application for the given settings."""
    configure_logging()
    settings.ensure_data_dir()
    configure_engine(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        from .migrations import upgrade_to_head

        upgrade_to_head(settings)
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
    "cash_flow",
    "downloads",
    "snapshots",
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
