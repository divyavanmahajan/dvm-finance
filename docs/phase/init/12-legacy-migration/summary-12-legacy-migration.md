# Summary: 12 — Legacy Migration from abn_analyst.db

## Completed
2026-07-08

## Goal
`abn-combined migrate-legacy <path>` imports all transactions, rules + conditions,
budgets, and tag data from the legacy database, idempotently, with a summary
(spec FR10).

## What Was Built
- `src/abn_combined/core/legacy_migration.py`: `migrate_legacy(path, settings)`.
  Opens the legacy SQLite strictly read-only (`sqlite:///file:...?mode=ro&uri=true`),
  reflects the schema via SQLAlchemy `MetaData.reflect`, and validates it against
  `REQUIRED_SCHEMA` (per-table required column sets captured from the real DB).
  Any missing table/column → `LegacyMigrationError` ("unknown legacy schema
  variant"), exit nonzero, zero writes. Copies `transactions` (ids + all 21
  columns verbatim, incl. manual_category/manual_tags/categorization_source),
  `categorization_rules` (numeric ids preserved so
  `transactions.categorization_source` rule-id references stay valid; fresh
  UUID generated per rule — legacy has no uuid column), `rule_conditions`, and
  `budgets`. Skips `users` and `alembic_version`. DATE columns coerced via
  `_as_date` (ISO string/datetime → `date`). Whole run is a single destination
  session transaction with rollback on any failure. Returns a
  `MigrationSummary` with per-table inserted/skipped and totals; re-runs skip
  existing ids and count them. Runs `ensure_data_dir` + alembic
  `upgrade_to_head` on the destination first.
- `src/abn_combined/cli.py`: replaced the `migrate-legacy` stub with
  `_run_migrate_legacy` — prints the formatted per-table summary + destination
  path, exit 0; `LegacyMigrationError`/`RuntimeError` → stderr message, exit 1.
- `tests/fixtures/legacy_fixture.py`: builds a fixture legacy DB from the
  verbatim DDL of the REAL `abn_analyst.db` (captured read-only), including the
  appended-column ordering the old `ensure_*` migrations produced, plus `users`
  and `alembic_version` tables that must be skipped. Seeds 5 transactions
  (manual overrides, rule-id source, all-NULL optionals), 3 rules (context
  filters, inactive, regex), 2 conditions (AND/OR + sort order), 2 budgets.
- `tests/test_legacy_migration.py` (16 tests): full-copy counts; field-fidelity
  spot checks (manual categories/tags, structured descriptions, priorities,
  conditions, context filters, budgets); unique rule UUIDs stable across
  re-runs; idempotent re-run all-skipped; unknown-schema + missing-columns +
  missing-file rejection; transactionality via injected `_copy_budgets` failure
  (nothing written); legacy file byte-identical after migration; CLI success /
  re-run / error-exit tests; first-run hint card tests.
- First-run hint (FR10 task item 4): minimal surgical extension of the existing
  empty-state block in `web/templates/_transactions_table.html` — when
  `page.total == 0` and no filter chips are active, a card shows the
  `abn-combined migrate-legacy /path/to/abn_analyst.db` command and links to
  Upload/Download. Filtered-empty keeps the "No transactions match" message.

## Real-DB Verification (on a temp copy — original never opened writable)
- `transactions` 6019, `categorization_rules` 701, `rule_conditions` 0,
  `budgets` 1 — all inserted on first run; per-table dst counts == src counts.
- Re-run: 0 inserted, 6721 skipped (idempotent, nothing changed).
- 8/8 `manual_category` rows preserved; three known transactions spot-checked
  byte-for-byte (incl. `transportation-glimble` with manual override `sweden`);
  rule 9 fields identical + valid UUID; 701 distinct rule UUIDs; **zero**
  orphaned `categorization_source` rule-id references.
- App started against the migrated data dir; headless-Playwright screenshots of
  the populated Transactions and Trends pages saved to
  `docs/phase/init/12-legacy-migration/screenshots/`.

## Key Decisions
- **Category hierarchy separator: hyphen (`-`)** — 627 of 701 rule categories
  contain a hyphen (e.g. `groceries-edeka`, `telecom-mobile`,
  `transportation-ovpay`); zero use `:`, `/` or `>`. Recorded here for the spec
  Open Question (architecture.md is shared-owned this wave, so noting here for
  the step-13 integration pass).
- Schema validation by required-column sets rather than exact DDL equality:
  tolerant of the legacy column-ordering drift caused by old `ensure_*`
  ALTER TABLEs, strict about the column inventory.
- All legacy rows are read up-front and the legacy engine disposed before any
  destination writes — the source file cannot be touched mid-migration.
- `is_active` NULL in legacy → `True` (matches legacy model default).

## Deviations
- The real DB's schema drift vs `app/database.py` is column *ordering only*
  (columns appended after `currency` by old ensure_* migrations); no missing or
  extra columns. Fixture reproduces the real ordering.
- Edited `_transactions_table.html` (step 06 territory) with one minimal
  additive block for the first-run hint — flagged for step 13 integration
  review; no restructuring of existing markup, filtered-empty behavior covered
  by a regression test.
- Replaced the obsolete `test_migrate_legacy_is_stub` in `tests/test_cli.py`
  with `test_migrate_legacy_missing_file_fails` (stub is gone by design).
- Step 11's in-flight `tests/test_snapshots.py` excluded from the final full
  run (imports `core.snapshots`, not yet created by the concurrent agent); all
  other 199 tests pass, ruff clean outside that file.
- Screenshot shows the Transactions page (task text says Trends in item 6,
  task checklist says Transactions) — both pages were captured.

## Files Changed
- `src/abn_combined/core/legacy_migration.py` (new)
- `src/abn_combined/cli.py` (stub → real subcommand)
- `src/abn_combined/web/templates/_transactions_table.html` (minimal hint-card edit)
- `tests/fixtures/legacy_fixture.py`, `tests/fixtures/__init__.py` (new)
- `tests/test_legacy_migration.py` (new, 16 tests)
- `tests/test_cli.py` (stub test replaced)
- `docs/phase/init/12-legacy-migration/screenshots/{transactions,trends}-real-data.png`
- `docs/phase/init/12-legacy-migration/summary-12-legacy-migration.md`
