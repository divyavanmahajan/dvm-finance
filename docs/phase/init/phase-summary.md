# Phase Summary: init

## Completed
2026-07-08

## What Was Built

The complete abn-combined application: a local, single-user FastAPI + SQLite web app (Jinja2 + htmx/Alpine, no JS build step) merging abn-download and abn-analyst. Nine tabs: Transactions (URL-encoded filter bar with chips/presets, inline manual edits, detail rows), Trends (category × period table with exact click-through), Rules (CRUD, dry-run preview diff, create-from-transaction, full change-report history), Tags, Budgets, Cash Flow, Download (ABN AMRO Playwright + PayPal CDP flows as background jobs with live status), Upload (MT940/XLS/CSV/PayPal/Wise/SEB), and Snapshots (versioned gzip export, incoming-wins transactional import with DB backup and audit report). Plus `migrate-legacy` (verified against the real abn_analyst.db: 6,019 transactions, 701 rules, idempotent, source untouched) and uvx-runnable packaging with the Alembic tree bundled in the wheel.

Test suite: 447 unit/integration tests + 6 e2e (five spec user flows) + 1 slow 50k-row perf test; coverage 88.84% with an enforced 80% gate; ruff clean.

## Key Architectural Decisions

- Ported (not rewritten) parsers, rule engine, and downloader protocol code from the legacy repos, with their tests; downloader modules kept diff-able against abn-download.
- Effective category/tags = manual value if set, else rule value; rule reapplication never touches manual fields; snapshot import is the only path that may overwrite them (explicit user action, fully reported).
- Every rule mutation (create/update/delete/toggle/recategorize/import) produces a persisted RuleChangeReport with per-transaction old→new diffs.
- All transaction-filter state lives in the URL query string (`core/filters.py`); trends/budgets/tags click-throughs are plain filtered-transactions links.
- Rules carry a UUID for cross-machine snapshot identity; transactions keep deterministic ids; `categorization_source` rule-ids are remapped via UUID on import.
- Category hierarchy separator is hyphen (`-`), confirmed from real data.
- Routers auto-register from `API_ROUTER_MODULES` (added to enable conflict-free parallel step execution).
- Schema changes via Alembic only; migrations run on startup from the wheel-bundled tree.

## Folder Structure Changes

`src/abn_combined/{api,core,downloaders,parsers,web}`, `alembic/`, `tests/` (+ `tests/e2e/`, `tests/fixtures/`), `docs/phase/init/` (spec, plan, per-step summaries + screenshots).

## How to Run / Test

```bash
source ~/venv/bin/activate
abn-combined --data-dir ~/abn-devdata            # run (http://127.0.0.1:8000)
abn-combined migrate-legacy <path-to-abn_analyst.db> --data-dir ~/abn-devdata
pytest                                            # unit + integration
pytest -m e2e                                     # browser e2e
pytest --cov=abn_combined                         # coverage (gate: 80%)
ruff check .
```

## Known Gaps / Follow-ups

- Real ABN AMRO and PayPal download flows are covered by mocked tests only — needs one manual session with live credentials.
- Package not yet published to PyPI (name `abn-combined` confirmed unclaimed 2026-07-08); use `uvx --from git+<repo-url> abn-combined` meanwhile.
- `demo.md` skipped: `showboat` is not installed on this machine. Per-step screenshots under each `docs/phase/init/*/screenshots/` serve as the visual evidence.

## Steps Completed
- [01-project-setup](./01-project-setup/summary-01-project-setup.md)
- [02-database-schema](./02-database-schema/summary-02-database-schema.md)
- [03-parsers-and-dedup](./03-parsers-and-dedup/summary-03-parsers-and-dedup.md)
- [04-rule-engine](./04-rule-engine/summary-04-rule-engine.md)
- [05-import-pipeline-and-upload](./05-import-pipeline-and-upload/summary-05-import-pipeline-and-upload.md)
- [06-transactions-view](./06-transactions-view/summary-06-transactions-view.md)
- [07-rules-ui](./07-rules-ui/summary-07-rules-ui.md)
- [08-category-trends](./08-category-trends/summary-08-category-trends.md)
- [09-tags-budgets-cashflow](./09-tags-budgets-cashflow/summary-09-tags-budgets-cashflow.md)
- [10-downloads-from-ui](./10-downloads-from-ui/summary-10-downloads-from-ui.md)
- [11-snapshot-sharing](./11-snapshot-sharing/summary-11-snapshot-sharing.md)
- [12-legacy-migration](./12-legacy-migration/summary-12-legacy-migration.md)
- [13-e2e-and-release](./13-e2e-and-release/summary-13-e2e-and-release.md)
