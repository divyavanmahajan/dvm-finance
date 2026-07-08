> **Initial draft** — scaffolded from spec interview. Updated by spec-execute as each phase completes.

# Architecture

Single Python package `abn_combined` serving a local, single-user, server-rendered web app.

| Layer | Choice |
|-------|--------|
| Language | Python 3.12+ |
| Web framework | FastAPI + Jinja2 templates |
| Frontend | htmx + Alpine.js (vendored), Pico.css — no build step |
| DB | SQLite (data dir via platformdirs), SQLAlchemy 2.x, Alembic migrations |
| Browser automation | Playwright sync API (ABN download), CDP attach (PayPal download) |
| Packaging | hatchling, `src/` layout, console script `abn-combined`, runnable via uvx |
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
