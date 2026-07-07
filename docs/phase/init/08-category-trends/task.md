# 08 — Category Trends View

## Goal
The Trends tab: hierarchical category × period table with totals, where any cell or row label links to the correspondingly filtered Transactions view.

## Context
Spec FR3 — the second main tab. No charts; the table with click-through is the feature.

## Prerequisites
06-transactions-view.

## Tasks
1. Aggregation query: SQL `GROUP BY` effective category × period (month default, year selectable) over a date window (default: last 12 full months), account filter; hierarchical rollup (parent categories subtotal their children — adopt the separator convention found in real data, see spec Open Questions), row totals, column totals, uncategorized row.
2. Route `GET /trends` with window/granularity/account controls in the same URL-state style as step 06.
3. Table rendering: sticky header/first column, negative amounts styled, empty cells blank. Each **cell** links to `/transactions?categories=<cat>&date_from=<period-start>&date_to=<period-end>` (+account); each **row label** links to the category over the full window. Sub-rows collapsible per parent (Alpine).
4. TDD first: aggregation unit tests (hierarchy rollup, month boundaries, manual-category precedence, uncategorized bucket), route tests asserting exact click-through URLs, then browser verification: click a cell → filtered transactions match the cell amount; screenshots.

## Acceptance Criteria
- Sum of a cell's linked transactions equals the cell value (asserted in an integration test).
- Row/column totals correct; hierarchy subtotals correct.
- Click-through works in the browser for both cells and row labels.
- `pytest` green, `ruff check .` clean, screenshots captured.

## Notes
- > ⚠ Golden Principle 8: click-through is just a filtered-transactions URL — no bespoke mechanism.
- Legacy reference: `abn-analyst/static/js/category-trends/` and `templates/category-trends.html`.
