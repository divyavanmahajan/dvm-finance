# Developer Guide

## Tech stack

- Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, Jinja2
- htmx + Alpine.js (vendored, no build step), Pico.css
- Playwright (downloads + e2e tests), connects to the installed Google Chrome over CDP — no
  bundled browser, no `playwright install`; platformdirs
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
                                # tests/test_snapshots_e2e.py); runs on the installed
                                # Google Chrome (channel="chrome") — install Chrome,
                                # no `playwright install` needed

# Run the app (dev). The command opens the browser at the app.
dvm-finance --data-dir ./devdata

# Run the app without a browser window.
dvm-finance --data-dir ./devdata --no-browser
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

- `DVM_FINANCE_DATA_DIR` / `--data-dir` — data directory (DB, downloads, snapshots)
- `DVM_FINANCE_LOG_ENV` — `production` selects the production log form; the
  default is `development`
- `DVM_FINANCE_NO_BROWSER` / `--no-browser` — do not open the browser at startup.
  Set the variable to any value that is not empty. The command otherwise waits
  for its own `/health` endpoint to answer, and then opens the default browser.
  The wait identifies the server by its data directory, so another program on the
  port never gets a browser window. The `migrate-legacy` subcommand opens none.
- `--port` (default 8000), `--host` (default 127.0.0.1). The command opens
  `127.0.0.1` when the host is `0.0.0.0`, which a browser cannot open.

Each variable carried the prefix `ABN_COMBINED_` before, which the earlier name
of the project left behind. The application still reads the old name of each
variable, and it writes a warning that names both. A later major version reads
the old names no more. The pairs live in `settings.py:LEGACY_ENV_NAMES`.
