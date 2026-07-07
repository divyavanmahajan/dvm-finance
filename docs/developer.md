> **Initial draft** — scaffolded from spec interview. Updated by spec-execute as each phase completes.

# Developer Guide

## Tech stack

- Python 3.12+, FastAPI, SQLAlchemy 2.x, Alembic, Jinja2
- htmx + Alpine.js (vendored, no build step), Pico.css
- Playwright (downloads + e2e tests), platformdirs
- Packaging: `src/abn_combined/` layout, hatchling, console script `abn-combined`

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
pytest                          # unit + integration
pytest --cov=abn_combined       # with coverage (gate: >= 80%)
pytest tests/e2e -m e2e         # Playwright e2e (starts app on a temp DB)

# Run the app (dev)
abn-combined --data-dir ./devdata
```

## Env vars / flags

- `ABN_COMBINED_DATA_DIR` / `--data-dir` — data directory (DB, downloads, snapshots)
- `--port` (default 8000), `--host` (default 127.0.0.1)
