# Tasks

## 1. Pinned header row

- [x] 1.1 In `TrendsView.swift`, add `@State horizontalOffset`, and store the offset in `updateCategoryWidth(offset:)`. Verify that the existing UI test `testTrendsCategoryColumnSettlesAtTheStart` still passes.
- [x] 1.2 Move the "Category" header out of `frozenCategoryColumn` and the header `GridRow` out of `valueColumns` into a header row above the vertical `ScrollView`, with the clipped header strip and `.offset(x: -horizontalOffset)` (design D1, D2). Verify on the iPhone 17 simulator, with the 12-month window, that the header stays at the top after a scroll down.
- [x] 1.3 Add a UI test in `TrendsCategoryUITests.swift`: scroll the rows down and check that the header still shows at the same y position; scroll the months to the right and check that the first visible month header and the value below it have the same horizontal center (within 1 point); tap the pinned "Category" header and check that its value changes to "Shows all names". Verify that the test passes.
- [x] 1.4 Verify at the largest Dynamic Type size that the header row and the body rows stay aligned, and save a screenshot. Verify that `xcodegen generate && xcodebuild test -scheme DVMFinance` passes.

## Workflow follow-up

- Test on a real iPhone in the next TestFlight build (build 6).
- Archive the change after the review and the merge.
