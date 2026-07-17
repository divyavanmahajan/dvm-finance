"""Help page: renders repo Markdown docs to HTML.

The user guide lives in ``web/help/features.md`` and the iOS companion-app
section in ``web/help/ios-app.md`` — kept as separate Markdown files so they can
be edited without touching templates or Python. Both are packaged with the app
(under the package tree, like the templates) so they render at runtime for a
``uvx``/``pip`` install.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import markdown
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

_HELP_DIR = Path(__file__).parent.parent / "web" / "help"
_MD_EXTENSIONS = ["extra", "sane_lists", "toc", "admonition"]


@cache
def _render_doc(name: str) -> str:
    """Read ``web/help/<name>.md`` and render it to HTML.

    Cached because the docs are static for a given install. Returns an empty
    string if the file is missing so a partial build still renders the page.
    """
    path = _HELP_DIR / f"{name}.md"
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    return markdown.markdown(text, extensions=_MD_EXTENSIONS, output_format="html")


@router.get("/help", response_class=HTMLResponse, include_in_schema=False)
def help_page(request: Request) -> HTMLResponse:
    from ..app import templates

    ctx = {
        "request": request,
        "active_path": "/help",
        "title": "Help",
        "features_html": _render_doc("features"),
        "ios_html": _render_doc("ios-app"),
    }
    return templates.TemplateResponse(request, "help.html", ctx)
