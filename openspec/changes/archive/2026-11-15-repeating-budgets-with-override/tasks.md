# Tasks

Use made-up categories and amounts in each test. Do not copy a value from the real data.

## 1. Data model

- [x] 1.1 Add an Alembic migration after `c81a4f73be20` that replaces the unique index `idx_budgets_category_period` with a plain index, and make the model match. State in the docstring that the downgrade fails when a pair holds two budgets. Verify with a test in `tests/test_migrations.py` that two budgets for one pair store after `upgrade head`.
- [x] 1.2 Add `find_overlap` and the boundary check to `core/budget_report.py`, with unit tests in `tests/test_budgets.py`: an open start, an open end, touching ranges, the exclusion of the budget under edit, and a start in the middle of a month. Verify that the tests pass.

## 2. Create, edit, and the add form

- [x] 2.1 Make `budget_create` and `budget_update` use `find_overlap` and the boundary check instead of the uniqueness check. Verify with client tests: a budget after an ended budget stores, an overlap shows the error that names the other budget, an overlapping update returns 400, and a start on the 15th returns 400.
- [x] 2.2 Remove the default validity end from the add form, and keep the start default. Keep both fields on the edit form. Verify with a client test that the add form has no end value and a start on the first day of the current period.

## 3. Period selector and sortable table

- [x] 3.1 Replace the reference date with the month selector on the Monthly tab and the year selector on the Yearly tab, with the `ref` fallback and the tab links that keep the selection (design decision 7). Move the create action into each tab. Verify with client tests: the default month and year, `month=2026-08` reports August, `year=2025` reports 2025, a malformed month returns 400, `ref=2026-08-15` selects August 2026, and the create link in each tab carries the selection.

- [x] 3.2 Add the sort parameter, the sort of the rows, and the header links to `api/budgets.py` and `_budgets_table.html`. Verify with client tests: the default puts the largest budget first, each column sorts both ways, a second click reverses the order, the status order, and an unknown sort falls back to the default.

## 4. Seed dialog and override

- [x] 4.1 Add `SEED_EXCLUDED_CATEGORIES` and `seed_budgets` to `core/budget_report.py`. Verify with unit tests: a new budget has no end, an override ends the old budget on the day before, an override in the start month changes the amount, a later budget limits the new end, and `income` and `transfer` never get a budget.
- [x] 4.2 Add `GET /budgets/seed` and the template `budgets_seed.html`, with the month input or the year input, the default selections, and the editable amounts. Verify with client tests: the default month and year come from the `start` parameter of the tab, with the current month or year as the fallback, an expired budget shows as no valid budget with the row selected, a valid budget shows with the row cleared, and the GET writes nothing.
- [x] 4.3 Add `POST /budgets/seed`, remove `POST /budgets/create-top-level`, and remove the old header button (task 3.1 adds the link in each tab). Verify with client tests that only the selected rows change, that an edited amount is stored, and that the Yearly tab multiplies the average by 12.
- [x] 4.4 Verify the full flow in a real browser against a copy of the data in `./devdata`: select a month on the Monthly tab and a year on the Yearly tab, open the dialog from each tab, change the month, override one category, and check the page for the old month and the new month.

## 5. Snapshot import

- [x] 5.1 Change `_merge_budgets` in `core/snapshots.py` to match on the category, the period, and the start only, and to delete and record each overlapping local budget. Verify with tests in `tests/test_snapshots.py` for both scenarios of the spec delta, and that an existing snapshot round trip still passes.

## 6. iOS data compatibility

- [x] 6.1 Add a GRDB migration after `v5` that replaces the unique budget index with a plain index. Verify with a test in `DatabaseTests.swift` that two budgets for one pair store.
- [x] 6.2 Change `SnapshotImporter.swift` to the same matching and overlap logic as `_merge_budgets`, and name the Python origin. Verify with tests in `SnapshotTests.swift` for the two spec scenarios, and that `BudgetSeedTests.swift` still passes.
- [x] 6.3 Run `xcodegen generate && xcodebuild test -scheme DVMFinance -destination 'platform=iOS Simulator,name=iPhone 17'`. Verify that all tests pass.

## 7. Docs

- [x] 7.1 Update the budget sections of `docs/product.md` and `web/help/features.md` in ASD-STE100: budgets repeat, the dialog, the override, the sort, the excluded categories, and the order "update the phone app before the first snapshot". Verify that the text matches the UI.

## 8. Integration checks

- [x] 8.1 Run `pytest`, `pytest --cov=abn_combined`, `pytest -m e2e`, and `ruff check .`. Verify that all pass and that the coverage stays at 80% or more.
- [x] 8.2 Run `openspec validate repeating-budgets-with-override --strict`. Verify that it passes.

## Workflow follow-up

- After the change ships, the user runs the dialog on the real data: the Monthly tab from November 2026, and the Yearly tab from 2027.
- A later change brings the sort, the repeat default, and the dialog to the iOS screens.
- Archive the change after the user accepts it.
