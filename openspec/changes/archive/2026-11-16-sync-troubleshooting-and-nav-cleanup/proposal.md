# Proposal

## Why

The iOS app shows "DVM Finance needs Local Network access" for each failure to
reach a LAN address. A user with the permission on gets this wrong message and
cannot find the real cause. The real cause is often an expired share or a
different Wi-Fi network. Also, on iOS the trends matrix wastes space between the
month columns, and the empty-state button for sample data has no label. On the
web app, the navigation bar holds 11 tabs, and two of them (Download and Upload)
have one purpose: to bring data in.

## What Changes

- iOS sync: the app classifies a download failure from the error that iOS
  returns, and does not guess from the address class:
  - iOS reports that the local network is prohibited: the app shows the
    Local Network message and the "Open Settings" button.
  - The computer refuses the connection: the app tells the user that the QR
    code expired or was used, and that the user must make a new QR code.
  - The connection times out, or the host is unreachable: the app tells the
    user to put both devices on the same Wi-Fi network. The app also names the
    VPN, the guest network, and the computer firewall as possible causes.
- iOS sync: the help text for the QR code sync gets a short list of these
  troubleshooting steps.
- iOS trends: the month and total columns become narrower, and the category
  column becomes narrower. More months fit on one screen, so the user can
  compare the months.
- iOS import tab: a new "Sample data" section loads or removes the sample data.
  The help tab keeps its controls.
- iOS transactions: the empty-state offer for sample data moves out of the list
  row. The "Load sample data" button shows its label and its normal height.
- iOS import tab: a red "Delete all data" button is the last section. A
  confirmation prompt warns the user before the app deletes anything.
- Web sample data: the web app gets the same fictional dataset as the iOS app.
  An empty Transactions page offers "Load sample data". The Import page and the
  Help page each hold a load or remove control. The web app refuses an export
  and a share while the sample data is present, as the iOS app does.
- Web navigation: the top bar becomes Transactions, Trends, Budgets, Cash Flow,
  Import, Cash, a QR icon, and Help. The "⋮" menu holds Export, Rules, Tags, and
  Duplicates.
- Web Import page: one page at `/import` holds the bank download sources and
  the statement upload form. **BREAKING** (bookmarks only): `/download` and
  `/upload` redirect to `/import`.
- Web Export page: the Snapshots page gets the name "Export" and the path
  `/export`. `/snapshots` redirects to `/export`. The POST endpoints under
  `/snapshots/…` do not change.
- Web QR icon: the icon opens the Export page and starts a new share at once,
  so the QR code shows after one click.

## Capabilities

### New Capabilities

- `sample-data`: the fictional dataset of the web application, its load and
  removal, its controls, and the refusal of an export while it is present.
- `ios-data-reset`: the "Delete all data" control of the iOS app, its
  confirmation, and the scope of the deletion.

### Modified Capabilities

- `app-runtime`: the navigation tabs, their order, and the overflow menu change.
- `statement-upload`: the upload form moves to the combined Import page.
- `statement-download`: the download sources move to the combined Import page.
- `snapshot-export`: the snapshots page gets the name "Export" and a new path.
- `snapshot-import`: the import report returns the user to the Export page.
- `snapshot-lan-share`: the QR icon in the navigation starts a share.
- `ios-snapshot-sync`: the app classifies a download failure from the iOS
  error, and not from the address class. The export refusal for sample data
  names the import tab too.
- `ios-category-trends`: the matrix uses compact columns.
- `ios-transaction-review`: the empty-state offer shows a labeled button of
  normal size.
- `ios-help`: the import tab also holds the sample data controls, and the QR
  code steps name the new Export page and the troubleshooting steps.

## Impact

- Swift: `DVMFinanceKit/Sources/DVMFinanceKit/Sync/QRSnapshotSync.swift` and its
  tests, `DVMFinance/Views/SyncFromComputerView.swift`, `TrendsView.swift`,
  `ImportView.swift`, `TransactionsView.swift`, and `HelpView.swift`.
- Swift (data reset): `DVMFinanceKit/Sources/DVMFinanceKit/Query/AppQueries.swift`,
  a new `DataReset.swift` in the same folder with its tests, and `ImportView.swift`.
- Python: `app.py` (`NAV_TABS`), `api/downloads.py`, `api/upload.py`,
  `api/snapshots.py`, `api/help.py`, `api/transactions.py`, a new
  `api/imports.py` for `/import`, a new `core/sample_data.py` (a port of
  `SampleDataset.swift`), a new `api/sample_data.py`, and `core/snapshots.py`
  (the export refusal).
- Templates: `base.html`, a new `import.html`, a new `_sample_data.html`,
  `transactions.html`, `help.html`, `download.html`, `upload.html`, and
  `snapshots.html`.
- Help content: `web/help/features.md`, `web/help/ios-app.md`, `README.md`, and
  `docs/product.md`.
- Tests: `tests/test_app_shell.py`, the route tests for download, upload, and
  snapshots, and the Playwright flows in `tests/e2e/test_flows_e2e.py`.
- No schema change. No change to the snapshot format. No change to the bind
  address.
