# Summary — 09 Tags, Budgets, Cash Flow

## Completed
2026-07-07

## Goal
Supporting tabs ported from abn-analyst: tag management (usage counts, rename with
full propagation, delete), budget CRUD with a budget-vs-actual table, and the
cash-flow income/expense summary — all tables, no charts (FR5–FR6).

## What Was Built
- `core/renames.py` (ported from abn-analyst `scripts/rename_category_or_tag.py`):
  - `rename_tag(db, old, new)` — updates `transactions.tags`,
    `transactions.manual_tags` and `rules.tags` (exact comma-separated part match,
    case-insensitive); `rename_category(db, old, new)` — updates both transaction
    category columns, `rules.category` and `budgets.category`, normalising the new
    value to lowercase; `delete_tag(db, name)` — removes the tag from both
    transaction tag columns (empties become NULL).
  - Audit (Golden Principle 5): every rule touched by a rename gets a stored
    `RuleChangeReport` (action `update`, before/after snapshots via
    `categorizer.rule_snapshot`, summary noting the rename). No rule reapplication
    is run — transactions are renamed in the same commit, so reapplying would only
    cause unrelated churn.
- `core/budget_report.py`: `get_period_dates(period, ref)` (year/month/Monday-start
  week windows), `compute_actual` — SQL `sum(abs(amount))` over the *effective*
  category (`coalesce(nullif(manual_category,''), category)`, manual precedence)
  with hierarchical prefix match (`food` matches `food:x` and legacy `food-x`),
  `budget_status` (over / near ≥80% / under), and `budget_vs_actual_table` applying
  validity dates (skips not-yet-active and expired budgets for the selected window).
- `core/cash_flow.py`: `generate_periods` (month/week/year windows clamped to the
  range) and `compute_cash_flow` — a single SQL GROUP BY (NFR2) bucketing by
  strftime month/year or SQLite `weekday 1` Monday, summing positive amounts as
  income and `abs(negative)` as expense; transactions whose effective category
  contains "transfer" are excluded (legacy semantics); `CashFlowResult` exposes
  per-period `net` and overall totals.
- `api/tags.py` — `GET /tags` (counts + credit/debit totals merged from both tag
  columns, deduped per transaction; each tag links to `/transactions?tag=<name>`),
  `POST /tags/rename`, `POST /tags/delete` (JS confirm).
- `api/budgets.py` — `GET /budgets` (`?period=` type filter + `?ref=` reference
  date in the URL), `POST /budgets/create` (duplicate category+period rejected
  inline), `GET /budgets/{id}/edit`, `POST /budgets/{id}/update`,
  `POST /budgets/{id}/delete`; category/actual cells link to the Transactions view
  filtered to category + period window via `TransactionFilter.to_query_string()`.
- `api/cash_flow.py` — `GET /cash-flow` with URL state
  (`?preset=|date_from=&date_to=&breakdown=&account=`, defaults: current year by
  month) and a `GET /cash-flow/table` htmx partial swapped on control change
  (consistent with step 06); per-period amounts and totals link to filtered
  transactions.
- Templates `tags.html`, `budgets.html` + `_budgets_table.html`,
  `budgets_edit.html`, `cash_flow.html` + `_cash_flow_table.html`; new stylesheet
  `web/static/tables.css` (data tables, over/near/under highlighting, status pills,
  inline forms, control bars) — `app.css` untouched.

## Key Decisions
- Rename audit writes lightweight per-rule `RuleChangeReport`s without reapplying
  rules (see above) — keeps history complete without recategorization side effects.
- `delete_tag` ports legacy semantics: transactions only, `rules.tags` untouched
  (editing a rule is a separate, audited action on the Rules page; the tag would
  legitimately reappear if the rule still assigns it).
- Budget actuals treat `sum(abs(amount))` as spend (legacy behaviour) and match
  both `:` (new) and `-` (legacy) hierarchy separators.
- Cash flow keeps the legacy transfer exclusion but drops the legacy
  income/fixed/variable section split for the simpler income/expense/net table the
  spec asks for.

## Deviations
- Cash-flow income/expense cell links cannot carry a sign filter — the filter model
  only supports `amount_min/max` on `abs(amount)` (filters.py is owned by step 06
  and was not modified). Cells link to the period window (+ account) without a
  sign restriction, as anticipated in the task notes.
- Legacy `/api/tags` `start_date`/`end_date` params were not ported; the tags page
  always shows all-time counts (no consumer of the date-filtered variant remains).

## Files Changed
- src/abn_combined/core/{renames,budget_report,cash_flow}.py (new)
- src/abn_combined/api/{tags,budgets,cash_flow}.py (new)
- src/abn_combined/web/templates/{tags,budgets,_budgets_table,budgets_edit,cash_flow,_cash_flow_table}.html (new)
- src/abn_combined/web/static/tables.css (new)
- tests/{test_renames,test_tags,test_budgets,test_cash_flow}.py (new, 57 tests)
- docs/phase/init/09-tags-budgets-cashflow/screenshots/{tags-list,budget-vs-actual,cash-flow}.png

## Verification
- `ruff check` clean on all step-09 files; full `pytest -q` green (399 passed,
  1 deselected slow) including all pre-existing tests.
- TDD red/green: rename-propagation units (rules + both tag columns + manual
  precedence intact), budget-vs-actual against hand-computed fixtures (period
  windows, validity dates, hierarchy, manual precedence), cash-flow aggregation
  units (hand-computed month totals, account filter, transfer exclusion via manual
  override, totals), route tests for all three pages incl. rename/delete/CRUD.
- Headless Playwright against a seeded temp data dir: tags list with counts and
  rename/delete controls, budget-vs-actual with an OVER row (housing 1450/1400)
  and linked actuals, cash flow Jan–Mar 2026 with net row — Jan expense 1580.40
  confirms the €500 transfer exclusion. Screenshots stored in this step's folder.
