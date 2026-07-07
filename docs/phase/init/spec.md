# abn-combined (init phase) — Specification

## Overview

`abn-combined` is a single integrated personal-finance application that merges the functionality of two existing projects: **abn-analyst** (FastAPI/SQLite statement analyzer with rule-based categorization) and **abn-download** (Playwright-based downloaders for ABN AMRO and PayPal). It is a local, single-user web application, shipped as a Python package runnable via `uvx`, with a lean server-rendered UI (Jinja2 + htmx + Alpine.js). Statement downloads are triggered from the web UI, transactions are categorized by user-defined rules (with manual override), and data can be shared with a second person via export/import snapshots.

This is the **initial project phase** (greenfield repo, porting proven logic from the two source projects).

## Problem Statement

Today the workflow spans two separate codebases: a CLI downloads statements and uploads them over HTTP to a separately running analyzer app that requires login. The analyzer carries unused weight (graphs, LLM integration, MCP servers, JWT auth) and its filtering UI is clunky. The user wants one coherent app covering download → import → categorize → review trends, plus the ability to share the dataset with one other person running the same app.

## Goals

- One application, one repo, one database: download, parse, categorize, and review in a single UI.
- Preserve the categorization engine exactly: rule types, match patterns, additional AND/OR conditions, priorities, context filters, tags, manual overrides.
- Make "create a rule from a transaction" a first-class, fast flow.
- Rule-change auditability: preview a rule's matches before saving, and keep a stored before/after change report for every rule edit.
- Category Trends table with click-through from any cell/row to the matching transactions.
- A redesigned, simple filtering experience on the Transactions view.
- Snapshot export/import so two people can share the dataset (incoming wins on conflict).
- Installable and runnable with `uvx abn-combined` (no checkout/venv required for the second user).
- One-time migration of all data from the existing `abn_analyst.db`.

## Non-Goals

- **No graphs/charts** (explicitly removed — they were not useful).
- **No LLM categorization** — rules + manual only; no API keys anywhere.
- **No MCP servers** (ports 8001/8002 from abn-analyst are dropped).
- **No authentication/login** — single local user; the server binds to localhost.
- **No Docker** — uvx only (the download flows need a local headed browser anyway).
- No live/concurrent multi-user database sharing (snapshots only).
- No natural-language query feature, no dashboard page, no Sentry.

## Users & Context

- Primary: Divya, running the app locally on macOS, downloading ABN AMRO and PayPal statements, categorizing with rules, reviewing category trends and budgets.
- Secondary: one other person with the same app installed via `uvx`, receiving snapshot exports and importing them (and possibly exporting back).
- Both are technical enough to run a terminal command but should not need a checkout, venv, or configuration to get started.

## Requirements

### Functional Requirements

**FR1 — Packaging & startup**
1. Distributed as a Python package with a `pyproject.toml` and console script `abn-combined`; runnable via `uvx abn-combined` (from PyPI or a git URL).
2. `abn-combined` starts the FastAPI server on `127.0.0.1:8000` (port configurable via `--port`/env) and prints the URL. A `--data-dir` flag / `ABN_COMBINED_DATA_DIR` env var overrides the default data directory (platform user-data dir via `platformdirs`, e.g. `~/Library/Application Support/abn-combined/`). The data dir holds the SQLite DB, downloaded statement files, and snapshot exports.
3. On first start, the database schema is created automatically (Alembic migrations run on startup).

**FR2 — Transactions view (main tab)**
1. Paginated, sortable transaction table: date, account, description, amount, currency, effective category, tags, categorization source.
2. Effective category = `manual_category` if set, else `category` (same precedence for `manual_tags` vs `tags`) — identical to abn-analyst semantics.
3. Inline edit of manual category and manual tags on a transaction (sets `categorization_source = "manual"`); clearing the manual value restores the rule-assigned one.
4. Row expansion (or detail panel) showing the structured description fields and source file/line.
5. **Redesigned filtering**: a single compact filter bar with: free-text search (description/counterparty), date range with quick presets (this month, last month, this year, last year, custom), category picker (hierarchical, multi-select, includes "Uncategorized"), tag picker, account picker, amount range, and a rule filter ("categorized by rule N"). Active filters render as removable chips. The full filter state is encoded in the URL query string so views are bookmarkable/shareable and the trends click-through can deep-link into it. htmx swaps the table without full page reloads.
6. "Create rule from this transaction" action on every row (FR4.6).

**FR3 — Category Trends view (main tab)**
1. Table of categories (hierarchical, with subtotals per parent category) × time periods (month by default; selectable year granularity and date window), cells showing summed amounts; row totals and per-period totals.
2. Clicking a **cell** navigates to the Transactions view filtered to that category + period; clicking a **row label** filters to that category over the whole window. Implemented as links carrying the filter query string (FR2.5).
3. Respects effective-category precedence and the same filter bar basics (account, date window).
4. No charts — table only.

**FR4 — Categorization rules**
1. Port the rule model unchanged: `priority` (lower = higher), `rule_type` (keyword, account_iban, structured_field, full_description), `match_pattern` (contains, exact, starts_with, ends_with, regex), `field_target`, `match_value`, `category`, `tags`, `is_active`, `notes`, context filters (`filter_account`, `filter_currency`, `filter_date_from/to`), and additional `RuleCondition`s (field/pattern/value with AND/OR operator and sort order).
2. Matching uses the ported `normalize_string_for_matching` semantics (lowercase, spaces stripped, `WERO/` removed).
3. Rules CRUD UI: list ordered by priority with active toggle, create/edit form with dynamic condition rows, delete with confirmation.
4. **Preview before save**: from the rule form, a "Preview matches" action evaluates the draft rule (without saving) and shows the transactions it would match, and — for edits — which transactions would *change* effective category/tags, including those the old version matched but the new one no longer does.
5. **Change report after save (audit)**: saving a rule (create, edit, delete, activate/deactivate) triggers reapplication of the rules to all non-manual transactions and stores a `RuleChangeReport`: timestamp, rule id, action, rule snapshot (before/after JSON), and per-transaction changes (transaction id, old category/tags → new category/tags). A "History" view lists reports per rule and globally; each report drills down to its changed transactions.
6. **Create rule from transaction**: from a transaction row, open the rule form pre-filled from that transaction (suggested match value from description/counterparty/IBAN, account filter, etc.), with the live preview (FR4.4) showing what it would match before saving.
7. Manual "Recategorize all" action that reapplies all rules to non-manual transactions and produces the same kind of change report.

**FR5 — Tags**
1. Tags management page (rename, delete, list with usage counts) ported from abn-analyst.
2. Rule-assigned tags vs manual tags with manual precedence, comma-separated storage as today.

**FR6 — Budgets & cash flow**
1. Port budget CRUD (category, amount, period year/month/week, optional validity dates) and the budget-vs-actual view (table, no charts).
2. Port the cash flow summary (income/expense per period, table form).

**FR7 — Downloads from the web UI**
1. A "Download" page with per-source actions:
   - **ABN AMRO**: starts the ported Playwright flow — a headed Chromium opens, the user authenticates with the mobile app, the app fetches MT940 files via the session (`mutationreporting/generations/v1`), saves them to the data dir, and imports them. Date range defaults to "since last successful download" per account (persisted), overridable in the UI.
   - **PayPal**: the ported CDP flow — connects to a user-launched Chrome with `--remote-debugging-port=9222` (the UI shows the exact command to start it), extracts the CSRF token, creates the report, polls status (progress shown in the UI via htmx polling), downloads the `.TXT` and imports it.
2. Download jobs run as background tasks in the server process; the page shows live status (pending / waiting for authentication / downloading / importing / done / failed with message). Only one download job per source at a time.
3. Every downloaded file is stored in the data dir and then parsed/imported through the same pipeline as manual upload, including dedup and rule application, ending with an import summary (new / duplicates skipped / categorized counts).

**FR8 — Manual upload**
1. Upload form accepting MT940/STA, ABN XLS, generic CSV, PayPal TXT, **Wise CSV**, and SEB files — all existing parsers ported with their tests.
2. Same dedup semantics as abn-analyst: deterministic transaction id from `account + date + amount + description_hash` (PayPal: `account + paypal_transaction_id`); `transaction_hash` retained for near-duplicate detection; exact duplicates silently skipped and counted.
3. After import, rules are applied to the new transactions; the result summary is shown.

**FR9 — Snapshot export/import (sharing)**
1. **Export**: one click produces a single versioned snapshot file (JSON, gzipped; schema version + export timestamp + source machine id) containing transactions (including manual categories/tags and categorization source), rules with conditions, budgets, and rule-change reports. Saved to the data dir and offered as a browser download.
2. **Import**: upload a snapshot file; the app validates the schema version, then merges: new records are inserted, and for records that exist in both, **incoming wins** (the snapshot value overwrites local, including manual categorizations and rule definitions). Rule identity across machines uses a stable UUID (`rules.uuid`) generated at creation, so the same rule edited on both sides matches up; transactions already have deterministic ids.
3. Import ends with a report: counts of inserted/updated/unchanged per entity, listed overwrites of locally-edited items, stored like a rule change report so it can be reviewed later. Import never deletes local records that are absent from the snapshot.

**FR10 — Migration from abn_analyst.db**
1. A one-time importer (CLI subcommand `abn-combined migrate-legacy <path-to-abn_analyst.db>` and/or a first-run UI prompt) copies transactions, rules + conditions, budgets, and tag data from the legacy schema into the new database, preserving ids, manual categorizations, and categorization sources. Users/auth tables are ignored.
2. Migration is idempotent (re-running skips already-present rows) and prints a summary.

### Non-Functional Requirements

- **NFR1**: Server binds to `127.0.0.1` by default; no auth means it must not listen on external interfaces unless the user explicitly passes `--host`.
- **NFR2**: Transactions view responsive with ≥ 50k transactions (indexed queries, server-side pagination; trend aggregation via SQL `GROUP BY`, not Python loops).
- **NFR3**: Rule reapplication + change-report generation for a full dataset completes in < 10 s at 50k transactions.
- **NFR4**: Frontend has no JS build step: htmx and Alpine.js are vendored static files; styling via a single vendored lightweight CSS framework (e.g. Pico.css) plus one custom stylesheet.
- **NFR5**: Playwright is a runtime dependency only for the download features and e2e tests; the app must start and work (upload/rules/trends) if Playwright browsers are not installed, showing a clear message with `playwright install chromium` instructions on the Download page.
- **NFR6**: Test coverage threshold ≥ 80% on the application package (excluding e2e).
- **NFR7**: Structured logging (ported `logging_config` approach) with `get_logger(__name__)` throughout.

## Architecture

```
┌──────────────────────────────── abn-combined (pip package) ───────────────────────────────┐
│  CLI entry (`abn-combined`) ── uvicorn ── FastAPI app (127.0.0.1:8000)                     │
│                                                                                            │
│  web/           Jinja2 templates + htmx/Alpine partials (Transactions, Trends, Rules,      │
│                 Tags, Budgets, Cash Flow, Download, Upload, Snapshots, History)            │
│  api/           Route modules (transactions, rules, tags, budgets, cash_flow, trends,      │
│                 upload, downloads, snapshots, migration)                                   │
│  core/          categorizer (rule engine + preview + change reports), dedup, models,       │
│                 snapshot export/import, legacy migration                                   │
│  parsers/       mt940, xls, csv, paypal, wise, seb, description (ported)                   │
│  downloaders/   abn (Playwright headed flow), paypal (CDP flow) — ported, refactored to    │
│                 run as background jobs with status reporting instead of CLI prompts        │
│  db: SQLite via SQLAlchemy 2.x + Alembic; data dir via platformdirs                        │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Technology**: Python 3.12+, FastAPI, SQLAlchemy 2.x, Alembic, Jinja2, htmx, Alpine.js, Playwright (sync API in worker threads for downloads), platformdirs, pytest (+pytest-cov), Playwright pytest for e2e, ruff for lint/format. Package layout: `src/abn_combined/`, built with hatchling.

**New/changed tables vs abn-analyst**: `rule_change_reports` (+ `rule_change_items`), `rules.uuid`, `download_state` (last successful download per source/account), `snapshot_imports` (import reports). Dropped: users/auth tables. Everything else ports over.

## Deployment

- `uvx abn-combined` (published to PyPI, or `uvx --from git+<repo-url> abn-combined` before publishing).
- First run: creates data dir + DB, prints URL; Download page guides through `playwright install chromium` when needed.
- No Docker, no reverse proxy, no service management — foreground process the user starts when needed.

## User Flows

1. **Download & import (ABN)**: Download tab → "Download ABN AMRO" (dates prefilled since last download) → Chromium opens → authenticate with mobile app → status updates in UI → import summary → link to new transactions.
2. **Categorize an uncategorized transaction**: Transactions tab → filter chip "Uncategorized" → row → "Create rule" → prefilled form → adjust match value → "Preview matches" shows matched/changed transactions → save → change report confirms what was recategorized.
3. **Review trends**: Trends tab → month columns for current year → click cell (e.g. Groceries × March) → Transactions view opens filtered to Groceries, March → drill into a transaction.
4. **Edit a rule safely**: Rules tab → edit rule → preview shows gains/losses vs current version → save → stored change report; later, Rules → History shows every change with its affected transactions.
5. **Share data**: Snapshots tab → Export → send file to partner → partner: Snapshots tab → Import → incoming-wins merge → import report shows inserted/updated/overwritten.
6. **First-time setup for partner**: `uvx abn-combined` → browser opens to empty app → import snapshot → full dataset available.

## Authentication and Authorization

None. Local single-user app bound to localhost (NFR1). Snapshot files contain financial data — the spec assumes users exchange them over a channel they trust; the app does not encrypt snapshots (documented in README).

## Data & Integrations

- **SQLite** in the data dir; schema managed exclusively by Alembic.
- **ABN AMRO**: session-authenticated `POST https://www.abnamro.nl/mutationreporting/generations/v1` after in-browser app auth; base64 MT940 payloads (as in abn-download).
- **PayPal**: QL API (`/reports/apis/common/ql`) via CDP-attached Chrome: `reportCreate` → `reports` polling → `download` (as in abn-download).
- **Legacy import**: direct read of `abn_analyst.db` (SQLAlchemy reflection against the old schema).
- **Snapshot file**: gzipped JSON, versioned schema documented in `docs/architecture.md`.

## Edge Cases & Error Handling

- Bank auth abandoned/timeout: download job moves to "failed — not authenticated in time"; browser closed; retry available.
- PayPal Chrome-with-CDP not running: clear instruction with the exact launch command; job fails fast, no hang.
- Duplicate imports (same file uploaded twice, overlapping date ranges): dedup by deterministic id; summary reports skipped counts.
- Regex rules with invalid patterns: validation error at save/preview time, never a 500 at match time.
- Rule reapplication never touches transactions with `categorization_source = "manual"` for category (manual precedence preserved).
- Snapshot import: schema-version mismatch → reject with message; corrupt file → reject; import runs in a transaction (all-or-nothing); the pre-import DB is backed up to a timestamped copy in the data dir first.
- Legacy migration against a live/locked DB or unknown schema variant → clear error, no partial writes (transactional).
- Port 8000 already in use → clear message suggesting `--port`.
- Data dir not writable → startup error naming the path and the `--data-dir` override.

## Constraints & Assumptions

- Single writer per database; no concurrent multi-machine editing (snapshots are the only sync mechanism, incoming wins).
- macOS is the primary platform (darwin paths in tests where relevant), but nothing platform-specific beyond Playwright/Chrome availability.
- ABN AMRO and PayPal internal APIs may change; downloaders are ports of currently working code, and their protocol assumptions are documented in `docs/references/`.
- The legacy `abn_analyst.db` at `/Users/divya/projects/abn-analyst/abn_analyst.db` is the migration source of truth.
- Reuse-not-rewrite: parsers, rule engine, dedup, and downloader internals are ported with their existing tests wherever possible.

## Testing

Red/green TDD throughout:

1. **Unit (pytest)**: rule engine (each rule type × match pattern × conditions × filters), normalization, dedup/id generation, parsers (fixture files per format, ported from both repos), snapshot export/import merge semantics (incoming-wins matrix), legacy migration mapping, trend aggregation.
2. **API/integration (pytest + TestClient)**: every route; filter query-string round-tripping; rule save → change-report generation; import summaries.
3. **E2E (Playwright, pytest-playwright)**: app started against a seeded temp DB; covers the five main flows above (except real bank/PayPal auth — downloaders are e2e-tested against a mocked HTTP layer; the true bank flows are verified manually). Trends cell click-through and create-rule-from-transaction with preview are mandatory e2e cases.
4. **UI verification during development**: each UI feature is additionally verified in a real browser (screenshots) before its step is marked done.
5. Coverage gate ≥ 80% (`pytest --cov`); `ruff check` clean before any step completes.

## Open Questions

- PyPI package name availability for `abn-combined` (fallback: run via `uvx --from git+…`).
- Whether the PayPal CDP flow should eventually launch its own Chrome instance instead of requiring a user-started one (out of scope for init; keep ported behavior).
- Category hierarchy conventions (separator, depth) — adopt whatever abn-analyst data uses (verify during migration step).

## Success Metrics

- Full legacy dataset migrates with zero lost transactions/rules/manual edits (row-count and spot-check assertions in the migration test).
- The five user flows pass as automated e2e tests and manual browser verification.
- Divya can retire both old projects: downloads, categorization, trends, budgets, and sharing all happen in abn-combined.
- Second user reaches a working, populated app with two commands (`uvx abn-combined` + snapshot import).
