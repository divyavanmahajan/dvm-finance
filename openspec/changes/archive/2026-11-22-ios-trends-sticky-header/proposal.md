# Proposal

## Why

On the iOS trends tab, the header row of the matrix scrolls away with the rows.
After a vertical scroll, the user cannot see which column is which month. The
user must scroll back to the top to read a value against its month.

## What Changes

- The header row of the matrix stays at the top of the matrix while the user
  scrolls the rows vertically. The header row holds the "Category" header,
  the month headers, and the "Total" header.
- The month headers stay aligned with their value columns during a horizontal
  scroll.
- The "Category" header stays aligned with the category column, keeps its
  width while the column changes width, and keeps its tap action (keep the
  column wide).
- The "Total" row at the bottom of the matrix does not change. It scrolls with
  the rows.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ios-category-trends`: a new requirement keeps the header row of the matrix
  visible during a vertical scroll.

## Impact

- Swift: `ios/DVMFinance/Views/TrendsView.swift` (the layout of `matrix`,
  `frozenCategoryColumn`, and `valueColumns`).
- UI tests: a new test in `ios/DVMFinanceUITests/TrendsCategoryUITests.swift`.
- No change to `DVMFinanceKit`, to the data, or to the web app.
- The change builds on the trends layout of PR #14
  (`feat/sync-troubleshooting-nav`), which is not merged yet.
