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
