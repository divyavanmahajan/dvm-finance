# 01 — Project Setup

## Goal
A pip-installable package skeleton where `abn-combined` starts an empty FastAPI app on 127.0.0.1:8000, with lint/test tooling wired and the base UI shell rendering.

## Context
Everything else builds on this: packaging (uvx requirement FR1), data-dir handling, logging, the no-build frontend stack, and the TDD tooling gates.

## Prerequisites
None.

## Tasks
1. Create `pyproject.toml` (hatchling, `src/abn_combined/` layout, Python 3.12+): deps `fastapi`, `uvicorn`, `jinja2`, `sqlalchemy>=2`, `alembic`, `platformdirs`, `python-multipart`; extras `dev` = `pytest`, `pytest-cov`, `httpx`, `ruff`, `playwright`, `pytest-playwright`.
2. Console script `abn-combined` → CLI (argparse or typer-free stdlib): flags `--port` (8000), `--host` (127.0.0.1), `--data-dir`; env `ABN_COMBINED_DATA_DIR`; subcommand structure ready for `migrate-legacy` (stub). Default data dir via `platformdirs.user_data_dir("abn-combined")`.
3. App factory `create_app(settings)` returning FastAPI with Jinja2 templates, static mount, and a health route. Startup fails with a clear message if the data dir is not writable; clear message if the port is busy (spec Edge Cases).
4. Port the structured-logging setup from abn-analyst (`get_logger(__name__)` pattern).
5. Vendor static assets: htmx, Alpine.js, Pico.css + one empty `app.css`. Base template `base.html` with nav tabs: Transactions, Trends, Rules, Tags, Budgets, Cash Flow, Download, Upload, Snapshots (placeholder pages render).
6. Tooling: `ruff` config, `pytest.ini`/`pyproject` test config with `e2e` marker, coverage config (gate ≥ 80% on `abn_combined`).
7. Tests first (TDD): CLI arg parsing, data-dir resolution/override, app factory serves base page and static assets, unwritable data dir error.
8. Verify `uvx --from . abn-combined` (or `pipx run`) starts and serves the shell; screenshot the rendered nav in a real browser.

## Acceptance Criteria
- `pip install -e ".[dev]"` then `abn-combined --data-dir ./devdata` serves the tabbed shell at http://127.0.0.1:8000.
- `uvx --from <repo-root> abn-combined` works.
- `pytest` green, `ruff check .` clean.
- Browser screenshot of the shell captured.

## Notes
- > ⚠ Golden Principle 9: no JS build step — assets are vendored files only.
- > ⚠ Golden Principle 4: default host must stay 127.0.0.1.

## External References
- `docs/references/fastapi-reference.txt`, `docs/references/htmx-reference.txt`, `docs/references/alpinejs-reference.txt`, `docs/references/platformdirs-reference.txt` — stubs exist; populate before use.
