# abn-combined

Integrated personal-finance app: download, parse, categorize, and review bank
statements locally. Merges the abn-analyst analyzer and the abn-download
downloaders into a single, local, single-user web application.

## Install & run

```bash
source ~/venv/bin/activate
pip install -e ".[dev]"
abn-combined --data-dir ./devdata
# -> http://127.0.0.1:8000
```

Or without a checkout:

```bash
uvx --from <repo-root> abn-combined
```

## Configuration

- `--data-dir` / `ABN_COMBINED_DATA_DIR` — where the SQLite DB, downloaded
  statements, and snapshot exports live (default: platform user-data dir).
- `--host` (default `127.0.0.1`), `--port` (default `8000`).

The app binds to `127.0.0.1` by default and has no authentication — do not widen
the bind address on an untrusted network.

## Notes

- No LLM, no MCP, no auth, no charts, no Docker.
- Frontend uses vendored htmx + Alpine.js + Pico.css (no JS build step).
- Snapshot files contain financial data and are not encrypted; exchange them
  over a channel you trust.
