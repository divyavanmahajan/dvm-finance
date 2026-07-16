# Architecture

Single Python package `abn_combined` serving a local, single-user, server-rendered web app.

| Layer | Choice |
|-------|--------|
| Language | Python 3.12+ |
| Web framework | FastAPI + Jinja2 templates |
| Frontend | htmx + Alpine.js (vendored), Pico.css — no build step |
| DB | SQLite (data dir via platformdirs), SQLAlchemy 2.x, Alembic migrations |
| Browser automation | Playwright sync API (ABN download), CDP attach (PayPal download) |
| Packaging | hatchling, `src/` layout, console script `abn-combined`, runnable via uvx; Alembic tree bundled into the wheel (`abn_combined/alembic{,.ini}` via force-include) so packaged installs migrate on startup |
| Auth | None (binds 127.0.0.1) |

```
CLI entry ── uvicorn ── FastAPI
   │
   ├─ web/          Jinja2 pages + htmx partials
   ├─ api/          transactions, rules, tags, budgets, cash_flow, trends,
   │                upload, downloads, snapshots, migration
   ├─ core/         rule engine + preview + change reports, dedup,
   │                snapshot export/import, legacy migration, models
   ├─ parsers/      mt940, xls, csv, paypal, wise, seb, description
   └─ downloaders/  abn (Playwright), paypal (CDP) — background jobs
```

## Data model (delta vs abn-analyst)

Ported unchanged: `transactions`, `categorization_rules` (+ new `uuid` column), `rule_conditions`, `budgets`.

New tables:
- `rule_change_reports` — id, created_at, rule_id/uuid, action (create/update/delete/toggle/recategorize/import), rule snapshot before/after (JSON)
- `rule_change_items` — report_id, transaction_id, old_category, new_category, old_tags, new_tags
- `download_state` — source, account, last_success_at, last_range_end
- `snapshot_imports` — import report metadata + counts

Dropped: users/auth tables, LLM/vector artifacts.

## Key invariants

- Effective category = `manual_category or category`; same for tags. Rule reapplication never overwrites manual values.
- Transaction id: deterministic `account + date + amount + description_hash` (PayPal: `account + paypal_transaction_id`).
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
