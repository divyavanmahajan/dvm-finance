# 12 — Legacy Migration from abn_analyst.db

## Goal
`abn-combined migrate-legacy <path>` imports all transactions, rules + conditions, budgets, and tag data from the legacy database, idempotently, with a summary.

## Context
Spec FR10 — one-time migration so the user starts abn-combined with their full history and rules.

## Prerequisites
02-database-schema (models); realistically run after 11 so migrated data is immediately viewable.

## Tasks
1. Implement the `migrate-legacy` CLI subcommand (stubbed in step 01): open the legacy SQLite read-only via SQLAlchemy reflection; refuse unknown schema variants with a clear error.
2. Copy `transactions` (preserve ids, all columns incl. manual_category/manual_tags/categorization_source), `categorization_rules` (+ generate `uuid` for each), `rule_conditions`, `budgets`. Skip users/auth and any LLM artifacts.
3. Idempotency: existing ids/rows skipped and counted; whole run transactional (no partial writes on failure).
4. First-run UI prompt: when the DB is empty, the home page shows a hint card pointing at the CLI command (no file-path upload UI needed).
5. TDD: build a fixture legacy DB (small dump created from the real schema of `/Users/divya/projects/abn-analyst/abn_analyst.db`); tests for full copy counts, field fidelity spot-checks (manual categories, rule conditions, priorities), re-run idempotency, unknown-schema rejection.
6. Final verification against the real `abn_analyst.db` (on a copy): row counts match per table; spot-check known transactions/rules in the UI; screenshot Trends with real data.

## Acceptance Criteria
- Migration of the real DB copy: zero lost transactions/rules/manual edits (count assertions printed in summary).
- Re-run reports all-skipped, changes nothing.
- `pytest` green, `ruff check .` clean.

## Notes
- Work on a **copy** of the real DB; never open the original read-write.
- Category hierarchy separator convention: confirm from real data here and record it in `docs/architecture.md` (spec Open Question).
