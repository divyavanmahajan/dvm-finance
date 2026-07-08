# Summary — 11 Snapshot Export/Import (Sharing)

## Completed
2026-07-08

## Goal
One-click export of a versioned snapshot file and an incoming-wins import with a
pre-import DB backup and a stored, reviewable import report (spec FR9).

## What Was Built
- `core/snapshots.py` (new service):
  - **Format**: gzipped JSON, `schema_version=1` header with `exported_at` and a
    `machine_id` (uuid persisted to `<data_dir>/machine_id`). Entities: transactions
    (every column incl. manual fields + `categorization_source`; dates ISO, numerics
    decimal strings), rules keyed by `uuid` with nested conditions (reuses
    `rule_snapshot()`), budgets (identity fields only, no machine-local id),
    rule_change_reports with nested items. Documented in `docs/architecture.md`
    ("Snapshot format" section, appended).
  - `export_snapshot(db, data_dir)` → `<data_dir>/snapshots/snapshot-<ts>.json.gz`;
    `list_exports` (name/modified/size, newest first); `read_snapshot(bytes)`
    validates gzip/JSON integrity, payload shape, and schema version — all failures
    raise `SnapshotError` with a clear message.
  - `import_snapshot(db, payload, db_path)`: backs the SQLite file up to
    `abn_combined.backup-<ts>.db` in the data dir, then merges in **one
    transaction** (rollback on any failure; `_pre_commit_hook` is the test seam for
    injected failures). Insert new rows; on collision **incoming wins** — including
    manual categorizations and rule definitions (the only path allowed to overwrite
    manual edits, per GP2, commented in code); never deletes local rows. Identity:
    transactions by deterministic id, rules by `uuid` (conditions replaced
    wholesale), budgets by `(category, period, start_date)` with a `(category,
    period)` fallback to respect the DB unique index. Incoming
    `categorization_source` values (machine-local rule ids) are remapped to local
    rule ids via the rule uuid map. Rule-change reports are matched on
    `(created_at, action, rule_uuid)` so re-imports don't duplicate the audit trail.
  - Rules are deliberately **not** reapplied after import — the snapshot's
    categorization state is authoritative (commented in code).
  - Import persists (inside the same transaction) a `SnapshotImport` row
    (per-entity inserted/updated/unchanged counts + field-level overwrite list) and
    an `action="import"` `RuleChangeReport` carrying per-transaction effective
    old→new category/tag changes, so it renders in the rules History list with the
    existing `.action-import` badge.
- `api/snapshots.py` (new router, claims `GET /snapshots` from the placeholder):
  - `GET /snapshots` — export button, past-exports table (name/date/size/download),
    import upload form, stored import reports (latest 20, just-imported highlighted).
  - `POST /snapshots/export` — writes the file and returns it as a download.
  - `GET /snapshots/files/{name}` — download past exports (names validated against
    the actual snapshots dir; no traversal).
  - `POST /snapshots/import` — rejected files re-render the page with the error at
    400; success redirects 303 to `/snapshots?imported=<id>`.
- Templates `snapshots.html` + `_snapshot_import_report.html`, new stylesheet
  `snapshots.css` (app.css untouched).
- Tests: `test_snapshots.py` (24 — export format/columns/uuid-keyed rules, stable
  machine id, export listing, version-mismatch + corrupt gzip/JSON/missing-header
  rejection, merge matrix new/identical/conflicting per entity, manual-category
  conflict → incoming wins with the overwrite listed, local-only rows preserved,
  categorization_source remap, report dedupe on re-import, no rule reapplication,
  backup bytes == pre-import DB, injected failure mid-import leaves DB unchanged,
  SnapshotImport + import RuleChangeReport persistence, full round-trip into a
  fresh DB), `test_snapshots_routes.py` (8 — page render, export download +
  listing + file download, traversal rejection, import round trip with report +
  backup, History renders the import badge, 400 rejections), `test_snapshots_e2e.py`
  (1, marked e2e — two live servers on two temp data dirs, real browser download
  from A, upload into B, incoming-wins verified, screenshots captured to
  `docs/phase/init/11-snapshot-sharing/screenshots/{export-list,import-report}.png`).

## Key Decisions
- Machine id is a uuid persisted per data dir (`machine_id` file), not the hostname —
  stable, unique, and no PII in the snapshot header.
- Transaction unchanged/conflict detection compares the *serialized* dicts (both
  sides go through the same export pipeline), avoiding Decimal/float drift.
- Reports lack a cross-machine uuid, so `(created_at, action, rule_uuid)` is used as
  a stable-enough identity for dedupe; local reports are never modified.
- The import's own audit report is excluded when comparing round-trip exports (B
  legitimately carries one extra `action="import"` report after importing).
- Overwrite lists store field-level `{local, incoming}` diffs per record so the
  report can show exactly what a locally-edited value was replaced with.

## Deviations
- Budget identity is `(category, period, start_date)` per the task, but the DB has a
  unique `(category, period)` index (from abn-analyst); when the triple doesn't
  match but the pair does, the import overwrites that row (incoming wins) instead of
  failing on the unique constraint. Noted in code.
- None otherwise; all acceptance criteria met.

## Files Changed
- src/abn_combined/core/snapshots.py (new)
- src/abn_combined/api/snapshots.py (new)
- src/abn_combined/web/templates/{snapshots.html,_snapshot_import_report.html} (new)
- src/abn_combined/web/static/snapshots.css (new)
- tests/{test_snapshots,test_snapshots_routes,test_snapshots_e2e}.py (new)
- docs/architecture.md (appended "Snapshot format" section)
- docs/phase/init/11-snapshot-sharing/{summary-11-snapshot-sharing.md,screenshots/*}

## Verification
- `ruff check .` clean; `pytest` 447 passed (415 baseline + 32 new); e2e browser
  test green with screenshots of the export list and the rendered import report.
