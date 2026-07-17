# Developer Guide

## Tech stack

- Python 3.12+, FastAPI, SQLAlchemy 2.x, Alembic, Jinja2
- htmx + Alpine.js (vendored, no build step), Pico.css
- Playwright (downloads + e2e tests), platformdirs
- Packaging: `src/abn_combined/` layout, hatchling, PyPI package `dvm-finance`, console script `dvm-finance`.
  The Alembic tree (`alembic.ini` + `alembic/`) is force-included in the wheel as
  `abn_combined/alembic{,.ini}` so packaged/uvx installs migrate on startup
  (`migrations.py` prefers the bundled tree, falls back to the repo root for
  editable installs).

## Environment

Use the shared virtualenv:

```bash
source ~/venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

## Commands

```bash
# Lint (gate for every step)
ruff check .

# Format
ruff format .

# Tests
pytest                          # unit + integration (e2e/slow deselected by default)
pytest --cov=abn_combined       # with coverage (fail_under = 80, wired in pyproject.toml)
pytest -m e2e                   # Playwright e2e: boots real app instances on random
                                # ports against seeded temp data dirs (tests/e2e/ +
                                # tests/test_snapshots_e2e.py); headless Chromium

# Run the app (dev)
dvm-finance --data-dir ./devdata
```

## E2E harness

`tests/e2e/conftest.py` provides `live_app` — a uvicorn subprocess on a free port
with a fresh temp data dir (Alembic migrates on startup) — plus `seed_transaction`
/ `seed_rule` helpers; tests drive it with the pytest-playwright `page` fixture.
The five spec user flows are covered by `tests/e2e/test_flows_e2e.py` (upload,
create-rule-from-uncategorized, trends click-through, edit-rule diff) and
`tests/test_snapshots_e2e.py` (two-machine snapshot sharing). Real bank/PayPal
download flows are covered by mocked tests only and re-verified manually.

## Env vars / flags

- `ABN_COMBINED_DATA_DIR` / `--data-dir` — data directory (DB, downloads, snapshots)
- `--port` (default 8000), `--host` (default 127.0.0.1)
