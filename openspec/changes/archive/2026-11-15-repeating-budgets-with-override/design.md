# Design

## Context

`budget_vs_actual_table` in `core/budget_report.py` computes the window that
holds the reference date for each budget, and it skips a budget whose validity
does not overlap that window. A budget with no end therefore already repeats.

Three places set an end or block a second budget:

- `_render` in `api/budgets.py` gives the add form the current window as the
  default for both validity fields.
- `budgets_create_top_level` sets `start_date` and `end_date` to the current
  window. It skips a category with any budget of the period, also an expired
  one.
- The index `idx_budgets_category_period` is unique. `budget_create`,
  `budget_update`, and `_merge_budgets` in `core/snapshots.py` all depend on
  this. The iOS schema (`AppDatabase.swift`) and `SnapshotImporter.swift` have
  the same index and the same fallback.

The real data holds 19 monthly budgets that ended in July or September, and 19
yearly budgets for 2026.

## Goals / Non-Goals

**Goals:**
- A budget repeats until the user ends it or overrides it.
- An override changes the amount from a selected month or year, and keeps the
  older amount for the earlier periods.
- The phone imports a snapshot with several budgets for one category.

**Non-Goals:**
- No change to the iOS screens. The iOS add form, the iOS seed action, and the
  iOS sort stay as they are. They still allow only one budget for each
  category, which is stricter than the new rule and therefore safe.
- No week tab. The week period keeps its current behavior, with the same
  boundary rule (Monday to Sunday).
- No automatic clean-up of the expired budgets. They stay as history.

## Decisions

### 1. A rule against overlap replaces the unique index

SQLite cannot enforce "no overlap" with an index. A new function
`find_overlap(db, category, period, start, end, exclude_id=None)` in
`core/budget_report.py` returns the first budget of the same category and
period whose range overlaps. An empty start is no lower limit, and an empty end
is no upper limit. `budget_create`, `budget_update`, and the seed use it.

The boundary rule (a start on the first day of a period, an end on the last
day) means that at most one budget of a category is valid in each window. The
report therefore needs no change. All stored budgets already meet the rule.

Alternative: keep one row and store a list of amounts with dates. This needs a
new table and a new snapshot format. We reject it.

### 2. The Alembic migration

A new migration after `c81a4f73be20` drops `idx_budgets_category_period` and
creates a plain index with the same name and columns. The downgrade creates the
unique index again. The downgrade fails when a pair holds two budgets. The
docstring of the migration states this.

The migration depends on the uncommitted merge migration `c81a4f73be20`.
Commit this change only after that work.

### 3. The dialog is a page with its state in the URL

The button becomes a link to `GET /budgets/seed?period=month&start=2026-11` (or
`period=year&start=2026`), inside each tab (decision 7). The page shows a month input or a year input, and a
table with one row for each top-level category with recent spend. A change of
the month or the year reloads the page through the URL. `POST /budgets/seed`
applies the selected rows. `POST /budgets/create-top-level` goes away.

Alternative: a Bootstrap modal that htmx loads. A page keeps the selection in
the URL, works with the back button, and needs no extra JavaScript. We choose
the page.

### 4. One function applies the seed

`seed_budgets(db, period, start, choices)` in `core/budget_report.py` takes a
list of `(category, amount)` pairs. For each pair it does these steps:

1. Find the budget that is valid on `start`.
2. If that budget starts on `start`, change its amount and notes.
3. Otherwise, if it exists, set its end to the day before `start`.
4. Find the next budget of the category that starts after `start`. The new
   budget ends on the day before that start, or it has no end.
5. Insert the new budget, with the notes of the seed.

The route builds the choices from the selected checkboxes and the edited
amounts. The function commits once. It returns the created, changed, and ended
budgets for the log.

### 5. The excluded categories

A constant `SEED_EXCLUDED_CATEGORIES = ("income", "transfer")` in
`core/budget_report.py` lists the top-level categories that the dialog never
shows. The actuals already exclude each category that holds `transfer`.

### 6. The average

The dialog uses `average_monthly_spend` with today as the reference. The
proposal therefore always reflects the three complete months before the current
month, also for a start in the future or the past.

### 7. A month or year selector replaces the reference date

The Monthly tab reads `?month=YYYY-MM` and shows an `<input type="month">`. The
Yearly tab reads `?year=YYYY` and shows a year `<select>` with the years that
hold transactions or budgets, plus the next year. A change submits the form, so
the URL holds the selection. The route converts the selection to the reference
date that `budget_vs_actual_table` already takes: the first day of the month or
year. A malformed value returns 400.

An old link with `?ref=YYYY-MM-DD` and no `month` or `year` selects the month or
year that holds that date. Only the budgets page itself writes `ref` today.

The create action is a link in the tab content, beside the selector. It passes
the selection: `/budgets/seed?period=month&start=<month>` or
`/budgets/seed?period=year&start=<year>`. The tab links keep the selection
when the user switches between Monthly and Yearly, as far as it applies: the
year of the selected month opens on the Yearly tab. From the Yearly tab, the
Monthly tab opens on the current month when the selected year is the current
year, and on January of the selected year otherwise.

### 8. Sorting on the server

The page reads `?sort=<column>_<asc|desc>`. The columns are `category`,
`period`, `window`, `budget`, `actual`, `remaining`, `used`, and `status`. The
default is `budget_desc`. The route sorts the rows after it computes them,
with the category as the second key. The header links follow the pattern of
the rules list (`rule_sort_url_for_column`). The status sorts in the order
`over`, `near`, `under`.

### 9. Snapshot matching

`_merge_budgets` matches on `(category, period, start_date)` only. With no
match, it deletes each local budget of the same category and period whose range
overlaps the incoming budget. It records each one in the overwrites list with
the field `deleted`. Then it inserts the incoming budget. The Swift
`SnapshotImporter` gets the same logic. A new GRDB migration replaces the
unique index.

## Risks / Trade-offs

- [The migration chain depends on uncommitted work.] → The tasks run the
  migration test on the current tree. The proposal names the order of the
  commits.
- [An old app version on the phone still has the unique index. A snapshot with
  two budgets for one category fails there.] → Update the phone app before the
  first snapshot with such a pair. The docs state it.
- [The desktop deletes a local budget when an incoming one overlaps it.] → The
  merge report names each deleted budget, as it does for each other overwrite.
- [The page now hides no budget that the user expects.] → An expired budget
  stays hidden in the later months, as before. The dialog shows that the
  category has no valid budget, and it selects the category.

## Migration Plan

1. Run `alembic upgrade head`. The app also does this at the start.
2. Open the Monthly tab, click the seed action, keep November 2026, and confirm
   the selected categories. The expired July and September budgets stay for
   their own month.
3. Open the Yearly tab, select 2027, and confirm, so that the yearly budgets
   continue after 2026.
4. Update the phone app, then export a snapshot for the phone.

Rollback: downgrade the migration only while each pair holds one budget.
