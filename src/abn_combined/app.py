"""FastAPI application factory."""

from __future__ import annotations

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

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["nav_tabs"] = NAV_TABS


def create_app(settings: Settings) -> FastAPI:
    """Build the FastAPI application for the given settings."""
    configure_logging()
    settings.ensure_data_dir()
    configure_engine(settings)

    app = FastAPI(title="abn-combined")
    app.state.settings = settings

    @app.on_event("startup")
    def _startup() -> None:
        from .migrations import upgrade_to_head

        upgrade_to_head(settings)
        logger.info("app_started", data_dir=str(settings.data_dir))

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


def _register_api_routers(app: FastAPI) -> None:
    """Register API routers. Guarded so partial builds still boot."""
    try:
        from .api.upload import router as upload_router

        app.include_router(upload_router)
    except ImportError:  # pragma: no cover - defensive during incremental build
        pass
