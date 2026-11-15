# Proposal

## Why

The user wants to set a monthly amount once and have it repeat for each
following month. The app already repeats a budget that has no validity end. But
the add form and the "Create budgets for top-level categories" action both set
the end to the last day of the current period. Each budget therefore expires
after one period. The page then hides it, and the action still counts it as
"already present", so the action creates nothing for that category.

The user also cannot change an amount from a given month on. The database
allows only one budget for each category and period, so a new amount replaces
the old amount for all months, also for the months in the past.

The action also creates a budget for `income`, which is not spend.

## What Changes

- A new budget repeats by default. The add form and the create action set no
  validity end.
- **BREAKING** (data model): one category can hold several budgets of one
  period, when their validity ranges do not overlap. An Alembic migration
  replaces the unique index on the category and the period with a plain index.
  A budget of a period starts on the first day of a period and ends on the
  last day of a period.
- The create action opens a dialog. The dialog asks for the start month (on the
  Monthly tab) or the start year (on the Yearly tab). It lists each top-level
  category with the proposed amount and the budget that is valid in that month
  or year, if there is one.
- In the dialog, the user selects each category to create or to override. An
  override ends the current budget on the day before the selected month or
  year, and starts a new budget there. The earlier months keep the old amount.
- The action and the dialog skip `income` and `transfer`.
- The budgets page replaces the reference date with a month selector on the
  Monthly tab and a year selector on the Yearly tab. The URL carries the
  selection. An old link with a reference date still works.
- The create action moves from the page header into each tab, beside the
  selector. The dialog starts with the month or year of the tab.
- The budget table sorts on each column. The default order is the budget amount,
  from the largest to the smallest. The sort lives in the URL.
- A snapshot import matches a budget by the category, the period, and the
  validity start. It no longer falls back to the category and the period.
- The iOS app gets the same data model and the same snapshot matching, so a
  snapshot with several budgets for one category imports on the phone. The iOS
  screens do not change in this change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `budgets`: the definition (several budgets for one category, period
  boundaries), the rule "One budget for each category and period" (it becomes a
  rule against overlap), the tabs (a month or year selector replaces the
  reference date), the add-form defaults, and the sort of the table.
- `budget-vs-actual`: the seed action moves into each tab and becomes a dialog
  with a start month or year, an override, and the exclusion of `income` and
  `transfer`.
- `snapshot-import`: the identity of a budget.
- `ios-budgets`: the phone stores several budgets for one category and matches
  an incoming budget in the same way as the desktop.

## Impact

- `alembic/versions/`: a new migration after `c81a4f73be20` (the uncommitted
  merge migration). This change can only be committed after that work.
- `src/abn_combined/core/models.py`, `core/budget_report.py`,
  `api/budgets.py`, `core/snapshots.py`.
- Templates: `budgets.html`, `_budgets_table.html`, `budgets_edit.html`, and a
  new dialog template.
- iOS: `Database/AppDatabase.swift` (a new GRDB migration),
  `Snapshot/SnapshotImporter.swift`, and their tests.
- Docs: `docs/product.md` and `web/help/features.md`.
- Data: the 18 expired July budgets and the 1 expired September budget stay as
  history for their own month. The user replaces them through the dialog. They
  do not repeat into later months. The 19 yearly budgets for 2026 end on
  2026-12-31, and the dialog can extend them from 2027.
