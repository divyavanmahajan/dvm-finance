# Summary — 01 Project Setup

## Completed
2026-07-07

## Goal
A pip-installable package skeleton where `abn-combined` starts a FastAPI app on
127.0.0.1:8000, with lint/test tooling wired and the base UI shell rendering.

## What Was Built
- `pyproject.toml`: hatchling build, `src/abn_combined/` layout, console script
  `abn-combined`, runtime deps (fastapi, uvicorn, jinja2, sqlalchemy>=2, alembic,
  platformdirs, python-multipart, structlog, pandas, openpyxl, xlrd) and `dev`
  extras. Ruff, pytest (`slow`/`e2e` markers, default-excluded), coverage config.
- `settings.py`: `Settings` + `resolve_data_dir` (arg > env > platformdirs),
  db/statements/snapshots paths, `ensure_data_dir` with writable check.
- `cli.py` / `__main__.py`: argparse CLI with `--host/--port/--data-dir`, a
  `migrate-legacy` stub subcommand, and port-in-use handling.
- `logging_config.py`: ported structlog `get_logger`.
- `db.py`: engine/session factory bound to the data-dir DB + `get_db`.
- `migrations.py`: alembic `upgrade_to_head` runner (no-op fallback until step 02).
- `app.py`: `create_app(settings)` factory — templates, static mount, `/health`,
  nav-tab placeholder pages, startup migration hook.
- Vendored static assets (htmx 2.0.4, Alpine 3.14.8, Pico 2.0.6) + `app.css`;
  `base.html` shell with the 9 nav tabs and `placeholder.html`.
- Tests: `test_cli.py`, `test_app_shell.py` (15 tests).

## Key Decisions
- Single `resolve_data_dir` helper reused by CLI and tests; probe-file writable check.
- Startup migration as a hook so step 02 wires alembic without touching create_app.
- API router registration guarded by try/except ImportError for incremental builds.

## Deviations
- Python runtime is 3.14 (venv), satisfies `>=3.12`.
- Used `@app.on_event("startup")` (deprecation warning); acceptable for now.

## Files Changed
- pyproject.toml, README.md
- src/abn_combined/{__init__,__main__,cli,settings,logging_config,db,migrations,app}.py
- src/abn_combined/web/templates/{base,placeholder}.html, web/static/app.css, web/static/vendor/*
- tests/{__init__,conftest,test_cli,test_app_shell}.py
- docs/phase/init/01-project-setup/screenshots/*.png

## Verification
- `ruff check .` clean; `pytest` 15 passed.
- `uvx --from . abn-combined --help` builds and runs; browser screenshot captured.
