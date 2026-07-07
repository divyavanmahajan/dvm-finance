# 11 — Snapshot Export/Import (Sharing)

## Goal
One-click export of a versioned snapshot file and an incoming-wins import with a pre-import backup and a stored, reviewable import report.

## Context
Spec FR9 — the mechanism that lets a second person on the same codebase share the dataset.

## Prerequisites
07-rules-ui (imports create change/import reports shown in History).

## Tasks
1. Snapshot format: gzipped JSON — header (schema_version, exported_at, machine id) + entities: transactions (all columns incl. manual fields and categorization_source), rules (keyed by `uuid`, with conditions), budgets, rule_change_reports/items. Document the schema in `docs/architecture.md`.
2. Export: service + `POST /snapshots/export` writing to the data dir `snapshots/` and returning the file as a browser download. Snapshots page lists past exports.
3. Import: upload → validate schema_version (mismatch → clear rejection) and integrity (corrupt → rejection) → back up the current DB to a timestamped copy in the data dir → merge in a single transaction: insert new rows; where ids/uuids collide, **incoming wins** (overwrite local, including manual categorizations and rule definitions); never delete local rows absent from the snapshot. Rule identity by `uuid`; transaction identity by deterministic id; budgets by (category, period, start_date).
4. Import report: persist `snapshot_imports` row with per-entity inserted/updated/unchanged counts and the list of overwritten locally-edited items; render after import and in History (step 07).
5. After import, run recategorize? **No** — snapshot carries final categorization state; do not reapply rules automatically (incoming state is authoritative). Note this in code.
6. TDD first: merge-matrix unit tests (new/identical/conflicting per entity type, manual-category conflict → incoming wins, local-only rows preserved), version-mismatch and corrupt-file rejection, backup created, transactionality (failure mid-import leaves DB untouched), export→import round-trip on a fresh DB reproduces the dataset. Route tests + browser verification of export/import between two temp data dirs; screenshots.

## Acceptance Criteria
- Round-trip: export from DB A, import into empty DB B → identical effective data.
- Conflict fixture: B's local edits overwritten by A's snapshot values, all listed in the import report; B-only rows untouched.
- Failed import leaves the DB byte-identical (backup + transaction verified by test).
- `pytest` green, `ruff check .` clean, screenshots captured.

## Notes
- > ⚠ Golden Principle 10: merges rely on deterministic ids and rule uuids — no fuzzy matching.
- > ⚠ Golden Principle 2 nuance: snapshot import is the *only* path allowed to overwrite manual edits, and only via explicit user action with a report.
