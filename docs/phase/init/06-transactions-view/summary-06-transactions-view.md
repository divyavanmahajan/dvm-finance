# Summary — 06 Transactions View with Redesigned Filtering

## Completed
2026-07-07

## Goal
The main Transactions tab (nav path `/`): paginated, sortable table with a compact
URL-encoded filter bar (chips + presets), inline manual category/tag editing with
precedence semantics, and expandable per-row detail. Filter state lives entirely in
the URL (Golden Principle 8).

## What Was Built
- `core/filters.py`: `TransactionFilter` dataclass — the single source of truth for
  the filter query string. Fields: `q`, `date_from/date_to`, `preset`
  (this-month/last-month/this-year/last-year), `categories[]` (hierarchical prefix
  match + special `uncategorized`), `tags[]`, `accounts[]`, `amount_min/max`,
  `rule_id`, `source_file`, `sort`, `page`. Round-trippable via
  `to_query_string()` / `from_query_string()` / `from_params(QueryParams)`; helpers
  `effective_dates()`, `resolve_preset_range()`, `active_chips()`, `without()`,
  `with_page()`, `with_sort()`. Plus the SQL layer: `build_query` (indexed filters,
  manual-precedence effective category/tags via `coalesce(nullif(manual,''), rule)`),
  `apply_sort`, and `paginate` (server-side offset/limit, `Page` with clamping and
  page metadata).
- `api/transactions.py`: `GET /` (Transactions tab) and `GET /transactions` alias so
  deep-links like `/transactions?rule_id=N` / `?source_file=...` from other steps
  resolve; `GET /transactions/table` htmx partial (chips + table + pagination);
  `GET /transactions/{id}/detail` detail partial; inline edit endpoints
  `POST/DELETE /transactions/{id}/category` and `.../tags` returning the swapped row.
  Facet helpers list known accounts/categories/tags for the filter bar.
- Templates: `transactions.html` (filter bar — search, preset + sort selects, an
  Alpine "more filters" disclosure with date/amount/account and category/tag
  multi-select dropdowns; a shared `#known-categories` datalist),
  `_transactions_table.html` (chips + count + table + pagination),
  `_transactions_row.html` (one `<tbody>` per txn so main+detail rows share Alpine
  state; inline category/tag editors with save/cancel/restore; "+ rule" link to
  `/rules/new?from_transaction=<id>`), `_transaction_detail.html` (structured fields,
  source file/line, categorization source with a link to the assigning rule).
- `web/static/js/transactions.js`: Alpine `txnFilterBar` — UI-only disclosure state
  (auto-expands when advanced filters are present in the URL); no filter state.
- `web/static/app.css`: filter bar, multi-select menus, chips, table, inline-edit,
  detail-panel, pagination styles; global `[x-cloak]` rule.

## Key Decisions
- Category filter uses effective category (`coalesce(nullif(manual_category,''),
  category)`) with hierarchical prefix match (`food` matches `food:restaurants`);
  `uncategorized` = effective category NULL/empty. Tags match via `contains` (legacy
  semantics). Amount range filters on `abs(amount)` (matches abn-analyst).
- Presets are serialised (not their resolved dates) so a bookmarked `this-month`
  re-resolves on reload; custom `date_from/date_to` used only when no preset.
- Clear-manual mirrors abn-analyst `transactions.py:448`: reset
  `categorization_source` to NULL only when it was `"manual"` and no other manual
  value remains (so clearing category keeps `manual` if manual tags persist).
- Each transaction is its own `<tbody>` (valid HTML) so the main row and its detail
  row share one Alpine scope; detail HTML is lazily fetched once via `hx-trigger="click once"`.
- Pagination clamps out-of-range pages to the last page.

## Deviations
- The "+ rule" link and detail "Create rule" button point at `/rules/new?from_transaction=<id>`
  (step 07); the URL is fixed now, target 404s until that step lands (as designed).
- `ruff check .` is clean for all step-06 files; the 15 remaining repo-wide ruff
  errors are entirely in step 10's concurrently-authored files (downloaders/,
  api/downloads.py, core/jobs.py, tests/test_jobs.py) and are owned by that step.

## Files Changed
- src/abn_combined/core/filters.py (new)
- src/abn_combined/api/transactions.py (new)
- src/abn_combined/web/templates/{transactions,_transactions_table,_transactions_row,_transaction_detail}.html (new)
- src/abn_combined/web/static/js/transactions.js (new)
- src/abn_combined/web/static/app.css (filter/table/chip/detail styles appended)
- tests/test_filters.py (new, 33 tests), tests/test_transactions.py (new, 23 tests)
- docs/phase/init/06-transactions-view/screenshots/{filter-bar,chips,inline-edit,detail-row}.png

## Verification
- `ruff check` clean on all step-06 files. Full `pytest -q`: 205 passed, 1 deselected
  (slow). 56 tests added (33 filter round-trip/preset/chip units + 23 TestClient tests
  covering every filter dimension, combinations, sort, pagination clamping, detail,
  inline edit + clear precedence, and rule-reapplication survival — Golden Principle 2).
- Headless Playwright against a seeded temp data dir (140 txns): captured filter bar,
  chips (verified bookmarkable — reload preserves URL), inline category edit, and the
  expanded detail row.
