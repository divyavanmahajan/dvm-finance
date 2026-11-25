# dvm-finance

Integrated personal-finance app: download, parse, categorize, and review bank
statements locally, in a single, local, single-user web application. No login,
no charts, no LLM — rules + manual categorization, tables, and an audit trail.

## Install & run (PyPI)

With PyPI, simply:

```bash
pip install dvm-finance
dvm-finance
```

Or with [uv](https://docs.astral.sh/uv/) for no-venv installation:

```bash
uvx dvm-finance
```

For development from a local checkout / wheel:

```bash
uvx --from /path/to/your/checkout dvm-finance
uvx --from dist/dvm_finance-0.1.0-py3-none-any.whl dvm-finance
```

## First run

```bash
dvm-finance             # serves http://127.0.0.1:8000 and prints the URL
```

On first start the app creates its data directory (SQLite DB, downloaded
statements, snapshot exports) and migrates the schema automatically. Defaults to
the platform user-data dir; the startup line prints the folder in use. Override
it with `--data-dir` or `DVM_FINANCE_DATA_DIR`. Other flags: `--port`
(default 8000), `--host` (default `127.0.0.1`) and `--no-browser` (do not open
the browser at the start).

The app binds to `127.0.0.1` and has **no authentication** — do not widen the
bind address on an untrusted network.

An empty install offers three ways in: migrate a legacy database (below), upload
statement files on the **Upload** tab (MT940/STA, ABN XLS, generic CSV, PayPal
TXT, Wise CSV, SEB CSV, First Tech OFX), or download directly from the **Download** tab.

## Migrating from abn-analyst

One-time, idempotent import of all transactions, rules + conditions, budgets and
manual categorizations from a legacy `abn_analyst.db` (opened read-only):

```bash
dvm-finance migrate-legacy /path/to/abn_analyst.db
```

Re-running skips already-present rows. A per-table summary is printed.

## Sharing data with a second person

- **Export** (Snapshots tab): one click writes a versioned, gzipped-JSON snapshot
  of transactions, rules, budgets and change reports, offered as a download.
- **Import** (their machine): upload the file on the Snapshots tab. The merge is
  **incoming wins** — new records are inserted, conflicting records (including
  manual categorizations and rule edits) are overwritten by the snapshot; local
  records absent from the snapshot are never deleted. The database is backed up
  first and an import report is stored for review.
- Second-user setup is two commands: `uvx dvm-finance`, then import a
  snapshot in the browser.

**Security note**: snapshot files contain your full financial data and are **not
encrypted**. Exchange them only over a channel you trust.

## Downloads

- **ABN AMRO**: click "Start ABN download" — a headed Chromium opens; authenticate
  with the ABN AMRO app; statements are fetched, saved and imported automatically.
  Requires Playwright browsers:

  ```bash
  playwright install chromium
  ```

  The app works fine without them (upload/rules/trends); the Download page shows
  install instructions when they are missing.

- **PayPal, Wise, SEB and First Tech**: start Chrome with remote debugging
  first, then click the start button of the bank. Log in to the bank in that
  Chrome window when the job asks. SEB needs the BankID login. First Tech gives
  one OFX file for all accounts and at most two years of history. For PayPal:

  ```bash
  /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --remote-debugging-port=9226 --user-data-dir=~/.chrome/debugdir \
    https://www.paypal.com/reports/dlog
  ```

SEB and First Tech amounts are converted to the euro with the ECB reference
rates. If the app cannot get the rates, it refuses the file and stores no
transaction. Try the import again later.

## Development

```bash
source ~/venv/bin/activate
pip install -e ".[dev]"
playwright install chromium

ruff check .                 # lint
pytest                       # unit + integration (e2e/slow deselected)
pytest --cov=abn_combined    # coverage (fails under 80%)
pytest -m e2e                # Playwright end-to-end flows (headless Chromium)
dvm-finance --data-dir ./devdata   # run against a scratch data dir
```

See `docs/architecture.md`, `docs/developer.md` and `docs/product.md` for design
notes, and `docs/core-beliefs.md` for the project's golden principles.
