# 06 — Transactions View with Redesigned Filtering

## Goal
The main Transactions tab: paginated sortable table, URL-encoded filter bar with chips and presets, inline manual category/tag editing, and row detail.

## Context
Spec FR2 — the most-used screen, and the click-through target for Trends (step 08). The filter design replaces the "clunky" legacy UI.

## Prerequisites
05-import-pipeline-and-upload.

## Tasks
1. Filter model: a dataclass parsed from/serialized to the query string — `q` (free text over description/counterparty), `date_from/date_to` + `preset` (this-month, last-month, this-year, last-year), `categories[]` (multi, hierarchical prefix match, special `uncategorized`), `tags[]`, `accounts[]`, `amount_min/max`, `rule_id`, `source_file`, `sort`, `page`. Round-trip unit tests first.
2. API/route: `GET /transactions` renders the page; `GET /transactions/table` returns the htmx partial (table + pagination) for the same query string. Server-side pagination and sorting; effective category/tags computed with manual precedence; indexed queries (NFR2).
3. Filter bar UI: compact single bar — search input, date preset dropdown + custom range, category/tag/account multi-select dropdowns (Alpine.js), amount range. Active filters shown as removable chips; every change updates the URL (`hx-push-url`) and swaps only the table.
4. Row interactions: expandable detail (structured description fields, source file/line, categorization source incl. link to the rule); inline edit of manual category (datalist of known categories) and manual tags — sets `categorization_source="manual"`; a clear control restores the rule value (source reset per legacy `transactions.py:448` behavior).
5. "Create rule" button per row linking to `/rules/new?from_transaction=<id>` (implemented in step 07; URL fixed now).
6. TDD: filter round-trip units; TestClient tests for each filter dimension and combinations, pagination, sorting, manual edit + clear endpoints. Browser verification: apply several filters, confirm URL is bookmarkable (reload reproduces view), screenshot.

## Acceptance Criteria
- All filter dimensions work individually and combined; reload of any filtered URL reproduces the exact view.
- Inline manual edits persist with precedence semantics; clearing restores rule values.
- 50k-row seeded DB paginates without noticeable lag.
- `pytest` green, `ruff check .` clean, screenshots captured.

## Notes
- > ⚠ Golden Principle 8: filter state lives in the URL — no client-side filter state outside the query string.
- > ⚠ Golden Principle 2: manual edits sacred — verify reapplication tests still pass after edit endpoints exist.

## External References
- `docs/references/htmx-reference.txt`, `docs/references/alpinejs-reference.txt`.
