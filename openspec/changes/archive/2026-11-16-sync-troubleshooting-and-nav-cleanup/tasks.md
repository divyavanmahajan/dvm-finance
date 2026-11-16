# Tasks

## 1. iOS: classify a failed QR sync download

- [x] 1.1 In `QRSnapshotSync.swift`, add the cases `.shareStopped` and `.computerUnreachable` with their user texts (ASD-STE100). Verify with a unit test that checks each `errorDescription`.
- [x] 1.2 Add the injected `PermissionProbe` to `SnapshotURLDownloader`, and the live `NWConnection` probe in `live()` (design D1). Verify that the existing tests compile with a fixed probe.
- [x] 1.3 Change the classification in `download(from:)`: the probe or the "Local network prohibited" path text gives `.localNetworkPermissionDenied`; `ECONNREFUSED` gives `.shareStopped`; another LAN failure gives `.computerUnreachable`; a public host keeps `.serverUnreachable`. Verify with new tests in `QRSnapshotSyncTests.swift` for each case, including a refused connection with the probe that reports "allowed".
- [x] 1.4 Replace `testConnectionFailureToLocalHostMapsToLocalNetworkPermission` and `testTimeoutToLocalHostAlsoMapsToLocalNetworkPermission` with tests for the new mapping. Verify that `xcodebuild test` passes for `DVMFinanceKit`.
- [x] 1.5 In `SyncFromComputerView.swift`, confirm that only `.localNetworkPermissionDenied` shows "Open Settings", and that the other cases show "Scan Again". Verify in the simulator with a QR code for a stopped share.
- [x] 1.6 In `HelpView.swift`, change the QR code steps to name the QR icon of the desktop application, and add the troubleshooting list (new QR code, same Wi-Fi, VPN, test the link in Safari). Verify on the simulator help tab.

## 2. iOS: compact trends matrix

- [x] 2.1 In `TrendsView.swift`, compute one value-column width for each table from the widest text, with 6 points on each side (design D2). Show each month header on two lines ("Oct" over "2026"), and give the header row of both matrix halves the height of two lines. Verify on an iPhone 16 simulator that the value columns are narrow and that the headers do not set their width.
- [x] 2.2 Give the category column a wide width (the longest label, with a maximum of half the screen width) and a narrow width (96 points, tail truncation). Read the horizontal offset in the coordinate space of the scroll view, and switch the width with an animation: narrow above 24 points, wide below 4 points (design D2). Verify on an iPhone 16 simulator in portrait: at rest, each name shows in full; after a scroll to the right, the column is narrow and at least four value columns show; after a scroll back, the names show in full again.
- [x] 2.3 Verify with the largest Dynamic Type size that a value of "-999.9K" shows on one line without truncation, and that the two halves of the matrix keep their rows aligned while the category column changes its width.

- [x] 2.4 Add the long press on a category name that shows the full name in a popover, plus the hint "Tap Category to show all names" while the column does not stay wide, with `.presentationCompactAdaptation(.popover)`, middle truncation, and a full-name `accessibilityLabel` (design D2a). Verify on the iPhone 17 simulator that a long press shows the full name and the hint, that the hint is absent while the column stays wide, that a tap still expands a group, and with VoiceOver (Accessibility Inspector) that the cell reads the full name.
- [x] 2.5 Make the "Category" header a toggle that keeps the column wide, with the state icon (design D2a). Verify on the simulator that the column stays wide during a scroll after one tap, and narrows again after a second tap and a scroll.

## 3. iOS: sample data controls and empty state

- [x] 3.1 Move the sample data section of `HelpView` into a new `SampleDataSection.swift`, which refreshes in `.task` and `.onAppear` (design D4). Verify that the help tab still loads and removes the sample data.
- [x] 3.2 Add `SampleDataSection` to `ImportView` with a short footer. Verify that a load in the transactions tab shows the remove control when the user opens the import tab.
- [x] 3.3 In `TransactionsView.swift`, move `emptyDatabaseOffer` from the list section to a `.overlay`, and hide the summary row while the database is empty (design D3). Verify on the simulator with an empty database that the button shows its icon, its label, and a normal height.
- [x] 3.4 Change the text of `SnapshotExporter.ExportError.sampleDataPresent` and of the empty-state description to name the import tab. Verify with the existing `SnapshotExporter` test, updated for the new text.

- [x] 3.5 Show full category and tag names in a transaction row and in the transaction detail: chips on their own line in a `FlowLayout`, and `CategoryChip`/`TagChips` with `wraps: true` (design D3a). Verify with a UI test that seeds a long category name and checks that the chip label is not truncated, and with a simulator screenshot.

## 4. iOS: delete all data

- [x] 4.1 Add `DataReset.deleteAll(db:)` in `DVMFinanceKit/Sources/DVMFinanceKit/Query/DataReset.swift` (design D10). Verify with a test that loads rows into each table, runs the reset, and finds each table empty and the schema intact.
- [x] 4.2 Add a test that lists the tables in `sqlite_master` and fails for a table that is neither reset nor in the kept list. Verify that it passes now, and that it fails when you add a temporary table.
- [x] 4.3 Add `AppQueries.deleteAllData(appDatabase:)`. It runs the reset in one write and then deletes the files in the snapshots folder, but not the `MachineID` marker. Verify with a test that an injected error rolls back each row, and that the machine identity stays the same after a reset.
- [x] 4.4 In `ImportView`, add the last section with the red destructive "Delete all data" button, the warning icon, and the confirmation prompt with the warning text, "Delete all data", and "Cancel". Verify on the simulator that "Cancel" deletes nothing, and that a confirm empties each tab and shows the sample data offer.
- [x] 4.5 Add a UI test in `DVMFinanceUITests` for the cancel path and the confirm path. Verify that `xcodegen generate && xcodebuild test` passes on the Mac.

## 5. Web: sample data

- [x] 5.1 Add `core/sample_data.py` as a port of `SampleDataset.swift`, with `load`, `remove`, `is_loaded`, and `is_database_empty` (design D9). Verify with unit tests for the load counts, a second load that adds nothing, a skipped budget, and a removal that keeps real rows.
- [x] 5.2 Add a parity test that fixes the ids, dates, amounts, and categories of the first and last rows for a fixed `today`. Add the matching Swift test in `SampleDatasetTests.swift`. Verify that both tests pass with the same values.
- [x] 5.3 Add `api/sample_data.py` with `POST /sample-data/load` and `POST /sample-data/remove`, and the `_sample_data.html` fragment. Verify with client tests for the htmx and non-htmx responses, and that a GET request changes no row.
- [x] 5.4 Show the offer on the Transactions page while `is_database_empty` is true, with a link to `/import`. Verify with a client test for an empty and a non-empty database.
- [x] 5.5 Add the sample data section to `help.html`. Verify with a client test that the Help page shows the load control or the remove control.
- [x] 5.6 Refuse the full export, the delta export, and `POST /snapshots/share` while the sample data is present. Verify with tests that no file is written, no share server starts, and the page shows the refusal text.
- [x] 5.7 Describe the sample data in `web/help/features.md` and `docs/product.md` (ASD-STE100). Verify that the Help page renders the new text.

## 6. Web: Import page

- [x] 6.1 Move the body of `download.html` to `_download_sources.html` and the body of `upload.html` to `_upload_form.html`. Move their context code into helper functions (design D6). Verify that the existing download and upload route tests still pass.
- [x] 6.2 Add `GET /import` with `import.html`. It holds the download sources, then the upload form, then the sample data section. Keep the JSON response of the non-htmx branch of `POST /api/upload` for API clients. Verify with client tests, and update `tests/test_downloads_routes.py` and `tests/test_upload.py`.
- [x] 6.3 Delete `download.html` and `upload.html`, and change `GET /download` and `GET /upload` to 307 redirects to `/import` that keep the query string. Verify with client tests for both redirects.

## 7. Web: Export page and the QR icon

- [x] 7.1 Change `GET /snapshots` to `GET /export`, change the title and heading to "Export", and change the import redirect to `/export`. Add a 307 redirect from `/snapshots` that keeps the query string. Verify with updated tests in `tests/test_snapshots_routes.py`.
- [x] 7.2 When the query holds `share=1`, render the `hx-trigger="load"` element and the `history.replaceState` script (design D7). Verify with a client test that a GET request starts no share, and with a Playwright test that the QR code shows after one click and that the address no longer holds `share=1`.

## 8. Web: navigation

- [x] 8.1 In `app.py`, split `NAV_TABS` into `NAV_TABS` and `NAV_MENU`, and register placeholders for both (design D5). Verify with `tests/test_app_shell.py`, updated for the new order.
- [x] 8.2 In `base.html`, render the top bar with the QR icon before Help, and render `NAV_MENU` in the "⋮" menu with the active state. Remove the old dropdown items. Verify with a client test for the order, the `aria-label` "Share to phone", and the active item on `/rules`.
- [x] 8.3 Update `tests/e2e/test_flows_e2e.py` and `tests/test_snapshots_e2e.py` for the new paths and labels. Verify that `pytest -m e2e` passes.
- [x] 8.4 Update `web/help/features.md`, `web/help/ios-app.md`, `README.md`, `docs/product.md`, and `docs/architecture.md` for the Import page, the Export page, the QR icon, and the new menu (ASD-STE100). Verify with `grep` that no user text names the "Snapshots" page or the Download and Upload tabs.

## 9. Integration checks

- [x] 9.1 Run `pytest`, `pytest --cov=abn_combined`, and `ruff check .`. Verify that all pass and the coverage stays at 80% or more.
- [x] 9.2 Open the web app in a real browser. Click each tab and each menu item, and use the QR icon. Verify that each page renders and the active state is correct.
- [x] 9.3 Build the iOS app for TestFlight and test on a real iPhone: permission off, an expired QR code, the phone on another network, and a good sync. Verify that each case shows the message that the spec requires. Result on 2026-11-16 (build 4): permission off, the phone on another network, and a good sync each showed the required message or result. The expired QR code case also showed the required message.
- [x] 9.4 Run `openspec validate sync-troubleshooting-and-nav-cleanup --strict`. Verify that it reports the change as valid.

## Workflow follow-up

- Archive the change after the review and the merge.
