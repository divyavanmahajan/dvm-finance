# Summary — 08 Category Trends View

## Completed
2026-07-07

## Goal
The Trends tab (FR3): hierarchical effective-category × period table with row/column/
grand totals, where every cell and row label is a plain filtered-transactions URL
(Golden Principle 8).

## What Was Built
- `core/trends.py`:
  - `TrendsParams` — URL-state dataclass for the /trends query string
    (`granularity` month|year, `date_from`, `date_to`, repeated `account`), same
    round-trip style as step 06's `TransactionFilter`. `default_window()` = the
    last 12 full months (current partial month excluded).
  - `aggregate(db, params)` — one SQL `GROUP BY strftime(fmt, transactiondate),
    lower(coalesce(nullif(manual_category,''), category))` with `SUM(amount)`
    (NFR2: aggregation in SQL, not Python loops); date window + optional account
    filter in the WHERE clause. Python only folds the grouped rows into the
    hierarchy: top-level parent = first hyphen segment, one sub-row per distinct
    full category value (including the parent's own exact transactions), an
    Uncategorized row (NULL and `''` accumulated together) pinned last, plus row
    totals, column totals and a grand total.
  - `build_periods()` — month/year columns covering the window, with the edge
    periods **clamped to the window** so a cell's link never selects transactions
    outside the aggregated range (matters for year granularity over a partial year).
  - `transactions_link(categories, date_from, date_to, accounts)` — builds the
    click-through URL via `TransactionFilter.to_query_string()`, guaranteeing the
    exact param names (`category`, `date_from`, `date_to`, `account`) stay in sync
    with core/filters.py forever.
- `api/trends.py`: `GET /trends` (full page, replaces the placeholder) and
  `GET /trends/table` (htmx partial swapped by the controls form with
  `hx-push-url`, step-06 style).
- Templates `trends.html` (window/granularity/account controls) and
  `_trends_table.html` (table partial with Jinja macros for amount/total cells;
  each parent group is its own `<tbody x-data="{open:false}">` with an Alpine
  toggle button and `x-show` child rows).
- `web/static/trends.css` (new stylesheet, app.css untouched): sticky header row +
  sticky first column + sticky totals footer inside a scroll container, negative
  amounts in red, blank empty cells, tinted parent rows, tabular numerals.

## Key Decisions
- **Hierarchy separator: hyphen (`-`).** Confirmed read-only against the legacy
  `/Users/divya/projects/abn-analyst/abn_analyst.db`: categories look like
  `groceries-ah`, `fixed-insurance-life`, `education-tuition-violin` (up to three
  segments, no `:` anywhere). Rollup groups by the first segment.
- **Parent links enumerate exact child categories.** core/filters.py prefix-matches
  hierarchies with `:` (`food` → `food:restaurants`), which does not match the
  legacy `-` convention, and filters.py is owned by step 06. Rather than a lossy
  prefix, a parent cell/row link carries every exact category in its subtree as
  repeated `category=` params (which filters.py ORs). This makes "linked
  transactions sum to the cell value" exact by construction; the integration tests
  assert it for every cell and row.
- Categories are lowercased in SQL (`lower(...)`) so casing variants aggregate
  together, matching the case-insensitive filter semantics of step 06.
- Two-level presentation (parent + full-category sub-rows) rather than arbitrary
  depth: matches the legacy "category level" UX while keeping the table readable;
  deeper names remain visible as full values in sub-row labels.
- A lone `auto-fuel` with no `auto` siblings still gets an `auto` parent group, so
  the top level is always the first-segment taxonomy.

## Deviations
- Task text sketched `?categories=<cat>`; the actual param name from
  core/filters.py is `category` (repeated), which the task also mandates
  ("use the exact query-param names from core/filters.py") — links use `category`.
- No `web/static/js/trends.js`: the only client behavior is the per-parent
  collapse, which is a one-expression inline Alpine `x-data`; a JS file would add
  nothing (Golden Principle 9 — keep it simple).

## Files Changed
- src/abn_combined/core/trends.py (new)
- src/abn_combined/api/trends.py (new)
- src/abn_combined/web/templates/trends.html (new)
- src/abn_combined/web/templates/_trends_table.html (new)
- src/abn_combined/web/static/trends.css (new)
- tests/test_trends.py (new, 24 tests), tests/test_trends_routes.py (new, 12 tests)
- docs/phase/init/08-category-trends/screenshots/{trends-table,trends-expanded-hierarchy,trends-cell-clickthrough}.png

## Verification
- TDD red/green: tests written first (module import failed), then implementation.
- `ruff check` clean on all step-08 files; full `pytest`: **399 passed, 1
  deselected (slow)** — includes all pre-existing tests.
- 36 tests added: window/period units (month boundaries, leap month, window
  clamping), manual-precedence, uncategorized bucket (NULL + ''), hierarchy
  rollup + parent category enumeration, totals, year granularity, account filter,
  params round-trip, exact link URLs; route tests asserting exact cell / parent /
  row-label / uncategorized / account-propagated hrefs; integration tests
  asserting **every** cell's and row-label's linked transactions sum to the
  displayed value via `TransactionFilter.from_query_string` + `build_query`.
- Headless Playwright against a seeded temp data dir (~700 txns over 12 months):
  captured the trend table, the expanded hierarchy (groceries/dining/fixed open),
  and the Transactions view after clicking the dining × Jul 2025 cell — the linked
  view showed exactly one transaction of −52.43 EUR, equal to the cell value.
