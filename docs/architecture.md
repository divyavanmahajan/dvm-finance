# Architecture

Single Python package `abn_combined` serving a local, single-user, server-rendered web app.

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ |
| Web framework | FastAPI + Jinja2 templates |
| Frontend | htmx + Alpine.js (vendored), Pico.css — no build step |
| DB | SQLite (data dir via platformdirs), SQLAlchemy 2.x, Alembic migrations |
| Browser automation | CDP attach to the user's installed Chrome (ABN + PayPal downloads) — no bundled browser |
| Packaging | hatchling, `src/` layout, PyPI package + console script `dvm-finance`, runnable via `uvx dvm-finance`; Alembic tree bundled into the wheel (`abn_combined/alembic{,.ini}` via force-include) so packaged installs migrate on startup |
| Auth | None (binds 127.0.0.1) |

```
CLI entry ── uvicorn ── FastAPI
   │
   ├─ web/          Jinja2 pages + htmx partials
   ├─ api/          transactions, rules, tags, budgets, cash_flow, trends,
   │                upload, downloads, snapshots, migration, manual
   ├─ core/         rule engine + preview + change reports, dedup,
   │                snapshot export/import, legacy migration, models,
   │                manual_txn (hand-entered transactions)
   ├─ parsers/      mt940, xls, csv, paypal, wise, seb, description
   └─ downloaders/  abn, paypal (both CDP via browser.py) — background jobs
```

## Data model (delta vs abn-analyst)

Ported unchanged: `transactions`, `categorization_rules` (+ new `uuid` column), `rule_conditions`, `budgets`.

New columns on `transactions` (migration
`alembic/versions/b3c1f0a27d44_add_manual_transaction_columns.py`):
- `is_manual` — `Boolean`, not null, server default false. True marks a
  hand-entered transaction. Each row that an import wrote reads as false.
- `deleted_at` — `DateTime`, nullable, indexed. A value marks a removal flag and
  records its time. `NULL` means live.

New tables:
- `rule_change_reports` — id, created_at, rule_id/uuid, action (create/update/delete/toggle/recategorize/import), rule snapshot before/after (JSON)
- `rule_change_items` — report_id, transaction_id, old_category, new_category, old_tags, new_tags
- `download_state` — source, account, last_success_at, last_range_end
- `snapshot_imports` — import report metadata + counts

Dropped: users/auth tables, LLM/vector artifacts.

## Key invariants

- Effective category = `manual_category or category`; same for tags. Rule reapplication never overwrites manual values.
- Transaction id: deterministic `account + date + amount + description_hash` (PayPal: `account + paypal_transaction_id`).
  A hand-entered transaction (`is_manual` true) is the one exception: its id is a
  UUID, because a content-derived id cannot survive an edit. See
  [Hand-entered transactions](#hand-entered-transactions-cash-is_manual-deleted_at).
- Rule matching normalization: lowercase, strip spaces, drop `WERO/` prefix (ported `normalize_string_for_matching`).
- All schema changes via Alembic.
- Snapshot merge: insert-or-overwrite (incoming wins), never deletes local rows; whole import is one transaction with a pre-import DB backup.

## Rules categorization (two-pass, v1.1.0+)

`core/categorizer.py:apply_rules` reapplies active rules to transactions in
**two passes**. Rules are split via `_split_rules` on the `CategorizationRule.is_tag_only`
column (new `Boolean`, default `False`, non-nullable):

1. **Pass 1 — category rules** (`is_tag_only=False`): applied in `priority`
   order (ties broken by `id`), **first match wins**, to non-manual
   transactions only (`categorization_source == "manual"` is skipped
   entirely). Writes `category`, `tags`, and `categorization_source`
   (`str(rule.id)`). A transaction with no matching category rule gets
   `category=None` (effective "Uncategorized").
2. **Pass 2 — tag-only rules** (`is_tag_only=True`): applied against **all**
   transactions, including manually categorized ones, and **regardless of
   priority order** — every tag-only rule that matches contributes its tags,
   not just the first. Tag-only rules never write `category` or
   `manual_category`; they only ever merge into `tags`.

Tag merging (`_merge_tags`) is a de-duplicating, order-preserving union: it
splits both the existing and incoming tag strings on `,`, appends any new tag
not already present, and rejoins with `,`. This means applying the same
tag-only rule twice, or having two tag-only rules emit overlapping tags, never
produces duplicate tags on a transaction.

Both passes route through the same `TxnChange` change list and
`record_rule_change` audit trail (see Hard rules in `CLAUDE.md`) — a
tag-only match that only changes `tags` is recorded the same way a category
change is, with `old_category == new_category` and `old_tags != new_tags`.

The `CategorizationRule` model gained one field for this: `is_tag_only:
Mapped[bool]`. A tag-only rule's `category` is always `None` (enforced in the
API layer's validation/draft-building, `api/rules.py`); its `tags` field is
required. The rules list UI (`web/templates/rules.html`) splits rules into
two sub-tabs (**Rules** / **Tag-only rules**) using the same `is_tag_only`
flag, and the snapshot format (below) round-trips `is_tag_only` as an ordinary
rule field.

## Transfer exclusion (default behavior)

**Default: All views exclude transfer categories by default** to reduce visual clutter
and focus financial reporting on actual spending rather than inter-account movements.

Transfer categories are identified by the `is_transfer_category()` helper in
`core/utils.py`, which checks if the effective category matches the pattern
`transfer*` (e.g., `transfer`, `transfer-wise`, `transfer-angelina`, etc.).

- **TransactionFilter** accepts `include_transfers: bool = False` parameter; URL query
  param `?include_transfers=1` restores them.
- **All aggregations** (trends, budgets, tags, rules match counts) respect this setting.
- **Manual category precedence** still applies: if a user manually categorizes a row
  as `transfer`, it will be excluded unless `include_transfers=1` is set.

UI toggles on Transactions, Trends, and Cash Flow pages allow users to toggle the setting
per-session (state lives in URL query params per Golden Principle 8). Rules preview also
has a toggle to test rule matches with/without transfers included.

## Hand-entered transactions (`CASH`, `is_manual`, `deleted_at`)

A hand-entered transaction records a payment that no statement reports, for
example a cash payment. `core/manual_txn.py` holds the rules and
`api/manual.py` holds the pages. `app.py` registers the router through
`API_ROUTER_MODULES` and adds the nav tab `("/manual", "Cash")`.

### The UUID identity and the two columns

An imported id holds the account, the date, the amount, and a hash of the
description. An edit of any of those values therefore produces a different row.
`core/manual_txn.py:create_manual_transaction` gives a hand-entered row a
`uuid.uuid4()` id instead, so `edit_manual_transaction` keeps the id and only
changes the values. The function recomputes `transaction_hash` and stamps
`updated_at`, so a delta snapshot carries the new values.

The UUID also makes the phone a first-class writer. Both devices create rows in
the same `CASH` account, each device mints its own ids, and the snapshot merge is
a union. No column records the device.

`is_manual` answers "which rows accept an edit and a flag". The pseudo account
cannot answer it, because a hand-entered correction may later belong in a real
bank account. `core/manual_txn.py:_get_manual_row` and
`api/manual.py:_get_manual_or_refuse` both read the column and refuse an
imported row with `ManualTransactionError` or HTTP 400.

Do not confuse the column `Transaction.is_manual` with the helper
`core/filters.py:is_manual(txn)`. The helper reports a **manually categorized**
transaction (`categorization_source == "manual"` or a `manual_category`). The
column reports a **hand-entered** transaction.

### The reserved pseudo account

`constants.CASH_ACCOUNT` is `"CASH"`, and `constants.is_reserved_account`
compares an account against it. `core/dedup.py:reject_reserved_account` raises
`ReservedAccountError` for a batch that holds a row for this account, and
`core/dedup.py:insert_transactions` calls it on every insert.
`core/importer.py` catches the error and reports the reserved account to the
user. The pseudo account stays fixed; the app offers no second pseudo account
and no user-named one.

The snapshot merge (`core/snapshots.py:_merge_transactions`) does not call
`reject_reserved_account`. It writes a `CASH` row like any other row, because
this is the path that shares the cash rows between the two devices.

### The flag, and the one shared exclusion predicate

`flag_manual_transaction` writes `deleted_at` and `restore_manual_transaction`
clears it. Neither deletes a row. A timestamp answers "since when" at the same
cost as a boolean, and it allows a later purge by age without a second
migration.

The transfer exclusion above binds the same set of readers with a separate SQL
clause in each one, and those clauses have already drifted in form. A reader that
misses such a clause does not fail loudly; it returns a total that still holds a
removed row. This exclusion therefore has one predicate:

```python
def live_only(query: Query) -> Query:      # core/filters.py
    return query.filter(Transaction.deleted_at.is_(None))
```

Seven readers compose it:

| Reader | Surface |
|--------|---------|
| `core/filters.py:build_query` | transactions list and its summary |
| `core/trends.py:aggregate` | category trends |
| `core/cash_flow.py:compute_cash_flow` | cash flow |
| `core/budget_report.py:compute_actual` | budget actuals |
| `api/tags.py:collect_tags` | tag usage counts |
| `api/rules.py:_matched_counts` | match count of each rule |
| `core/categorizer.py:preview_rule` | rule preview |

Two surfaces do **not** compose it, on purpose:

- The snapshot export query in `core/snapshots.py` keeps a flagged row, so the
  flag reaches each other machine.
- The id set in `core/dedup.py:check_duplicates` keeps the id of a flagged row,
  so no second row claims it.

A test walks the seven readers and asserts that each one hides a flagged row.
The test is the control, because the failure is silent.

### The flag crosses a snapshot

The snapshot format and its `schema_version` of 1 do not change. The export
already writes every column of `transactions`, so `is_manual` and `deleted_at`
travel with it. `core/snapshots.py` lists `deleted_at` in
`_TXN_DATETIME_COLUMNS`, so the import parses it back to a `datetime`. The
import rule is unchanged: incoming wins per present row.

This gives one useful property. A machine purges a row, a second machine still
holds the row with its flag, and the next snapshot returns the row to the first
machine. The row returns flagged, so it stays out of each list and each total.
The purge needs no tombstone.

A flag and a restore on two machines resolve by the order of the imports. The
merge replaces the local values and does not compare `updated_at`. This is an
accepted limitation.

An older application that reads a newer snapshot ignores the two fields, and it
therefore shows a flagged row.

### The purge

`core/manual_txn.py:purge_flagged_transactions` is the one function that deletes
a transaction row.

Caution: ask the user to confirm the purge before you call this function. The
app cannot undo it.

1. The function calls `core/snapshots.py:_backup_db`, the same helper as the
   snapshot import, and copies the SQLite file to a timestamped backup beside
   it.
2. It deletes each row with a value in `deleted_at`, and no other row.
3. It returns the number of the deleted rows.

`api/manual.py:manual_purge` is the only caller. It refuses the request until the
form field `confirm` holds one of `CONFIRM_VALUES`, and it then reads the
database path from `request.app.state.settings.db_path`.

A rollback of the Alembic migration drops the two columns. A rollback after a
purge cannot return the purged rows; only the backup of the purge holds them.

## Category hierarchy convention

**Separator: hyphen (`-`), up to three segments** — e.g. `groceries-ah`,
`fixed-insurance-life`, `education-tuition-violin`. This is the convention the
legacy `abn_analyst.db` data uses (627 of 701 rule categories contain a hyphen;
none use `:`, `/` or `>` — verified read-only during the migration step, resolving
the spec Open Question). The canonical separator is exported as `CATEGORY_SEPARATOR`
from `core/utils.py` and used consistently across filters, trends, and budgets.
Trends rolls categories up by the first hyphen segment; parent cell/row links
enumerate the exact child categories as repeated `category=` params so linked
transaction lists sum exactly to the displayed cell.

## Snapshot format

A snapshot (FR9) is a single **gzipped JSON** file, written by `POST /snapshots/export`
to `<data_dir>/snapshots/snapshot-YYYYMMDD-HHMMSS.json.gz` and offered as a browser
download. Producer/consumer: `core/snapshots.py`.

Top-level shape (`schema_version` 1):

```json
{
  "header": {
    "schema_version": 1,
    "exported_at": "2026-07-08T10:30:00",
    "machine_id": "<uuid persisted in <data_dir>/machine_id>"
  },
  "transactions": [ { "...every transactions column..." } ],
  "rules": [ { "...rule fields incl. uuid...", "conditions": [ { } ] } ],
  "budgets": [ { "category", "amount", "period", "start_date", "end_date", "notes" } ],
  "rule_change_reports": [ { "...report fields...", "items": [ { } ] } ]
}
```

- **transactions** — every column of the `transactions` table, including
  `manual_category`, `manual_tags` and `categorization_source`. Dates are ISO strings,
  numerics are decimal strings.
- **rules** — the `rule_snapshot()` shape: all rule fields plus nested `conditions`.
  Identity across machines is `uuid`; the integer `id` is machine-local and only used
  to remap `categorization_source` on import.
- **budgets** — identity is `(category, period, start_date)`; the machine-local `id`
  is not exported.
- **rule_change_reports** — full audit trail with nested `items`
  (per-transaction old→new category/tags). Matched on import by
  `(created_at, action, rule_uuid)` so re-imports do not duplicate the trail.

Import contract (`POST /snapshots/import`):

1. Validate: corrupt gzip/JSON or a `schema_version` other than the supported one is
   rejected with a clear message; nothing is written.
2. Back up the SQLite file to `<data_dir>/abn_combined.backup-YYYYMMDD-HHMMSS.db`.
3. Merge in **one transaction**: insert new rows; on identity collision **incoming
   wins** (including manual categorizations and rule definitions — the only path
   allowed to overwrite manual edits, by explicit user action); local rows absent
   from the snapshot are never deleted. Incoming `categorization_source` rule ids are
   remapped to local rule ids via the rule `uuid`.
4. Persist a `snapshot_imports` row (per-entity inserted/updated/unchanged counts +
   field-level list of overwritten locally-differing records) and an
   `action="import"` `rule_change_reports` row carrying the per-transaction effective
   category/tag changes (renders in the rules History list).
5. Rules are **not** reapplied after import — the snapshot's categorization state is
   authoritative.

Snapshots are not encrypted; users exchange them over a channel they trust (see spec).

### Delta snapshots

`POST /snapshots/export-delta` (form field `since`, a `datetime-local` value; empty
falls back to the stored last-delta-export marker, or the epoch if that's unset too)
writes a **delta** snapshot to `<data_dir>/snapshots/delta-YYYYMMDD-HHMMSS.json.gz` —
the same format as a full snapshot, except:

- `header` carries two extra keys: `"delta": true` and `"since": "<iso8601>"`, making
  the file self-describing.
- `transactions` is limited to rows with `updated_at >= since` (rows with a `null`
  `updated_at` — never touched since that column was added — are excluded).
  `updated_at` is stamped by every write that changes `category`/`manual_category`/
  `tags`/`manual_tags`/`categorization_source`: manual set/clear (`api/transactions.py`),
  `bulk_set_tags`, and rule-driven recategorization (`core/categorizer.py:apply_rules`).
- `rules`/`budgets`/`rule_change_reports` are still exported **in full** — only
  `transactions` is filtered. A delta is "a snapshot with fewer transactions," nothing
  more.
- Export advances the `export_state` table's `last_delta_export_at` marker to the
  export's start time, so the next delta export defaults to "changes since this one."

**Import is unchanged** — the same incoming-wins-per-present-row, never-delete-absent-
rows merge already has exactly the right semantics for a partial transaction set, so no
special-case delta merge logic exists. The only import-side addition is provenance:
`snapshot_imports` gained `is_delta`/`delta_since` columns, populated from the header
and surfaced in the import history list (`_snapshot_import_report.html`) so a delta
import is visibly distinguishable from a full one.

Intended use: lightweight device-to-device sync of just recent edits (e.g. from the iOS
app, which ports this same `since`-filtered format) without re-transferring the entire
transaction history each time.
