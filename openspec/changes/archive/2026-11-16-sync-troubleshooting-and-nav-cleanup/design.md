# Design

## Context

See `proposal.md` (Why) for the motivation. The current state that shapes the
approach:

- `SnapshotURLDownloader.download(from:)` in
  `DVMFinanceKit/Sources/DVMFinanceKit/Sync/QRSnapshotSync.swift` maps each
  `URLError` of a connection class to `.localNetworkPermissionDenied` when
  `QRSyncPayload.isLocalNetworkHost(url)` is true. The code ignores the cause of
  the failure.
- On the Mac, the one-shot share server listens on `0.0.0.0` at a random port.
  After the download or after 10 minutes, the server stops. Then a connection
  to that port gets a TCP reset, so the phone gets "connection refused". Today
  the phone shows the Local Network message for this case.
- `TrendsView.swift` gives each value column a frame of 88 points plus 8 points
  of padding on each side, so each column is 104 points wide. The widest
  compact value ("-999.9K" in the caption font) is about 50 points wide. The
  category column is 160 points plus 16 points of padding.
- `TransactionsView.swift` puts `emptyDatabaseOffer` (a `ContentUnavailableView`
  with a `.borderedProminent` button) inside a `Section` of an
  `.insetGrouped` `List`. The list row constrains the action area, so the
  button stretches vertically and loses its label.
- The web navigation is `NAV_TABS` in `app.py`, rendered in `base.html`. A
  "⋮" dropdown in `base.html` already holds Download, Upload, Snapshots, and
  Duplicates.

## Goals / Non-Goals

**Goals:**
- Show the error message that matches the real cause of a failed QR sync.
- Keep the classification testable without a network.
- Keep each old web URL working through a redirect.

**Non-Goals:**
- No change to the share server, its port, its token, or its bind address.
- No change to the snapshot format or to a database schema.
- No new iOS tab. The iOS tab set stays as it is.
- No change to the download jobs, the upload pipeline, or the snapshot import.

## Decisions

### D1. Classify the iOS failure in three steps

`download(from:)` classifies a transport error in this order:

1. **Permission.** The app asks the Network framework about the path to the
   same host and port. It opens an `NWConnection` with a short limit (about 2
   seconds). If the state is `.waiting` and
   `connection.currentPath?.unsatisfiedReason == .localNetworkDenied`, the
   result is `.localNetworkPermissionDenied`. As a fallback, the app also
   checks the `URLError` user info: the `_NSURLErrorNWPathKey` description
   contains "Local network prohibited".
2. **Refused.** The error code is `.cannotConnectToHost`, and the underlying
   POSIX error is `ECONNREFUSED` (61). The app reads it from
   `NSUnderlyingError` or from `_kCFStreamErrorCodeKey`. The result is a new
   case `.shareStopped`, with the text "The QR code expired or was already
   used…".
3. **Other.** The error is a timeout, an unreachable host, or a lost
   connection to a LAN host. The result is a new case `.computerUnreachable`,
   with the Wi-Fi, VPN, guest-network, and firewall text. A public host keeps
   `.serverUnreachable`.

The probe in step 1 is an injected closure, `PermissionProbe: (URL) async ->
Bool`, next to the `Transport`. The unit tests inject a fixed answer. The
`live()` factory injects the `NWConnection` probe.

Alternatives:
- *Only the string match of the user info.* This is a private key, and its
  text can change in a new iOS version. Use it only as the fallback.
- *A Bonjour browse to trigger and read the permission.* This needs a
  `NSBonjourServices` entry and a service on the Mac. It is more work, and the
  `NWPath` reason gives the same answer.

Only the permission case keeps the "Open Settings" button in
`SyncFromComputerView`. The view already keys the button on
`.localNetworkPermissionDenied`, so it needs no change for that.

### D2. Compact trend columns from measured text

`TrendsView` computes one value-column width for each table. It measures the
widest string among the cells, the totals, and the period labels. It uses
`UIFont.monospacedDigitSystemFont` at the size of the caption text style, so
Dynamic Type still works. The width is that value plus 6 points on each side.
The category column has two widths:

- **Wide (at rest):** the width of the longest visible category label, plus
  the chevron, the indent of a child row, and the padding. The app measures
  the labels with the same font metrics. The width has a maximum of half the
  screen width, so that one very long name cannot hide the values.
- **Narrow (after a scroll):** 96 points, with a one-line label that truncates
  at the tail.

A `GeometryReader` in the background of the value grid reads the x position
of the grid in the coordinate space of the horizontal `ScrollView`. The
negative of that value is the offset. A change of the category width moves
the scroll view and the grid together, so it cannot change the offset. (An
earlier version compared two global positions from two readers. They updated
in two passes, so a width change gave a false offset for one pass, and the
column wobbled at the start position.) This works on iOS 17, the deployment
target. (`onScrollGeometryChange` needs iOS 18.) The column becomes narrow
when the offset is more than 24 points, and wide again only when it is less
than 4 points. Between the two values the width does not change, so the
bounce at the start position cannot switch it. The change uses a short
`withAnimation`. Both halves of the matrix keep the same row height, so the
rows stay aligned while the width changes.

The screenshot of the current build (iPhone, 393 points wide) shows the
category column at about 176 points and each month column at about 104
points. Only two months show, and the Total column is off the screen.

A one-line header "Oct 2026" in the bold caption font is about 58 points
wide, so it would set the column width to about 70 points. Then four months
do not fit (128 + 4 × 70 = 408 points). For month periods, the header row
therefore shows the short month name on the first line and the year on the
second line. The header row gets the height of two lines. The values then set
the width.

With "-999.9K" at about 50 points, each column is about 62 points. On a
390-point iPhone, the narrow category column (about 104 points with padding)
and four value columns (about 248 points) fit after a scroll, which the spec
requires. At rest, the wide column shows the full names and fewer months. A year period keeps
its one-line label ("2026").

Alternative: a fixed narrower constant, for example 64 points. That fails for
a large Dynamic Type size, and it wastes space when all values are small.

### D2a. The full category name on request

The tap on a category row expands or collapses a group, so the full name needs
another gesture:

- **Long press:** `categoryCell` gets `.onLongPressGesture` (about 0.4 s). It
  sets a `@State var fullNameRow: String?`, and a `.popover` on the cell
  shows the full label. On iPhone, add
  `.presentationCompactAdaptation(.popover)`, so the popover does not become a
  sheet. The label of a child row is already the full category value, so
  the popover shows the label as it is. The cell is a plain view with a tap
  gesture and a long-press gesture, not a `Button`: a disabled button for a
  leaf row would also stop the long press.
  While `keepCategoryWide` is false, the popover shows a second line in the
  secondary style: "Tap Category to show all names", with the
  `arrow.left.and.right` icon of the header. The long press is the moment the
  user needs the hint, so the header toggle needs no other onboarding.
- **Middle truncation:** the label uses `.truncationMode(.middle)`. A child
  name then keeps its last segment, which is often the part that differs.
- **Header tap:** the "Category" header becomes a button that toggles
  `@State var keepCategoryWide`. `updateCategoryWidth` ignores the offset
  while the value is true. The header shows `arrow.left.and.right` when the
  column stays wide, and no icon in the automatic state.
- **VoiceOver:** the cell sets `.accessibilityLabel` to the full name.

Alternatives: two-line labels (rows become taller, so fewer rows fit), and a
tap that scrolls the months back (it conflicts with the tap that expands a
group).

### D3. Empty-state offer as an overlay

`TransactionsView` removes the `Section { emptyDatabaseOffer }` from the
`List`. It adds `.overlay { if isDatabaseEmpty { emptyDatabaseOffer } }` to the
`List`. The overlay keeps the navigation title, the search field, and the
toolbar. The `ContentUnavailableView` then sizes its button normally. While the
database is empty, the list also hides the summary row, so the overlay does not
cover it.

### D3a. Full category and tag names in a transaction row

`TransactionRow` puts the chips in a narrow column next to the amount, and
`CategoryChip` has `lineLimit(1)`. A long category such as
"education-tuition-chelseaballet" then shows as "education-tuition-chelseabal…".

- The row gets two parts: the description and the amount on the first line,
  and the chips below them across the full width of the row.
- A new `FlowLayout` (a SwiftUI `Layout`, iOS 16 and later) puts the chips on
  as many lines as they need.
- `CategoryChip` and `TagChips` get a `wraps` option. With `wraps: true`, the
  text has no line limit, so a long name wraps at a hyphen or a space. The
  chip uses a rounded rectangle with a radius of 10 points, which looks like a
  capsule on one line and stays tidy on two lines.
- The transaction detail view uses the same layout. Other screens (budgets,
  pickers) keep one line.

### D4. One shared sample-data view for the help tab and the import tab

The load and remove logic in `HelpView.sampleDataSection` moves into a new view,
`SampleDataSection`, in `DVMFinance/Views/SampleDataSection.swift`. `HelpView`
and `ImportView` both use it. The view refreshes its state in `.task` and in
`.onAppear`, so a load in another tab shows when the user returns. The view
keeps the existing `AppQueries` calls. The text of the footer in the import tab
is shorter: it tells the user to remove the sample data before an export.

### D5. Web navigation as two data lists

`app.py` replaces `NAV_TABS` with two lists:

- `NAV_TABS`: Transactions `/`, Trends `/trends`, Budgets `/budgets`,
  Cash Flow `/cash-flow`, Import `/import`, Cash `/manual`, and Help `/help`.
- `NAV_MENU`: Export `/export`, Rules `/rules`, Tags `/tags`, and Duplicates
  `/merge`.

`base.html` renders `NAV_TABS`. It inserts the QR icon (`bi-qr-code`, link
`/export?share=1`, `aria-label` and `title` "Share to phone") before Help. It
renders `NAV_MENU` in the "⋮" dropdown. The placeholder loop iterates over
both lists. A dropdown item gets the `active` class when its path is the
active path. The dropdown toggle also gets the `active` class then, so the
user can see where the user is.

### D6. Import page from two partials

The body of `download.html` moves to `_download_sources.html`. The body of
`upload.html` moves to `_upload_form.html`. A new `import.html` includes both,
with the download sources first. A new route `GET /import` builds the context
of both pages. The context code moves into helper functions in
`api/downloads.py` and `api/upload.py`, so that `/import` and the tests use
one source. The non-htmx branch of `POST /api/upload` keeps its JSON response,
because API clients use it. The form on the Import page uses htmx, so the user
stays on the Import page.
`download.html` and `upload.html` are deleted.

### D7. Export page and the auto share

`GET /snapshots` becomes `GET /export`. The template `snapshots.html` keeps its
name, and only its title and heading change to "Export". The snapshot import
POST redirects to `/export`. The POST endpoints under `/snapshots/…` and
`/snapshots/files/{name}` keep their paths, so the share server and the tests
stay stable.

When the query holds `share=1`, the template renders one extra element:
`<div hx-post="/snapshots/share" hx-trigger="load" hx-target="#share-qr">`. An
inline script calls `history.replaceState` to remove the query. The GET handler
starts nothing, so a prefetch or a crawler cannot start a share.

### D8. Redirects

`/download`, `/upload`, and `/snapshots` return status 307 to the new path, and
keep the query string. A 307 is not cached as permanent, so a later change of
the path stays possible.

### D9. Web sample data as a port of the Swift dataset

The sample dataset exists only in Swift today
(`DVMFinanceKit/Sources/DVMFinanceKit/Query/SampleDataset.swift`). This is the
one place where Python ports from Swift. The new module
`core/sample_data.py` names that origin in its docstring. It copies the line
items, the budget list, the account number, the id prefix `sample-`, the note
"Sample budget", the sequence numbering, the "wobble" factor, and the two-place
rounding. It uses `budget_report.get_period_dates` for the budget ranges. A
parity test fixes the first and last rows of a load for a fixed `today`, with
the same values as a matching Swift test.

- `load(db, today)` inserts rows with `category` set, `is_manual` false, and
  `categorization_source = "sample"`. It does not call `apply_rules`, so it
  writes no rule change report.
- `remove(db)` deletes `Transaction.id LIKE 'sample-%'` and
  `Budget.notes == 'Sample budget'`, and returns the two counts.
- `is_loaded(db)` and `is_database_empty(db)` mirror the Swift functions. A
  live transaction has `deleted_at IS NULL` and `merged_into IS NULL`.

Routes in a new `api/sample_data.py`: `POST /sample-data/load` and
`POST /sample-data/remove`. Each returns the `_sample_data.html` fragment for an
htmx request, and a 303 redirect to the referer otherwise. The fragment shows
the current control and the result message. `transactions.html`, `import.html`,
and `help.html` include it. On the Transactions page, the fragment shows only
while `is_database_empty` is true. After a load there, the response sends
`HX-Refresh: true`, so the page shows the new rows.

`core/snapshots.export_snapshot` and the delta export raise a new
`SampleDataPresent` error while `is_loaded` is true. `POST /snapshots/share`
checks the same condition before it exports. Each route shows the refusal text
in the place where it shows a result today.

Alternative: a separate database file for the sample data. This needs a second
engine and a switch in each query. The id prefix and the note keep the same
isolation with no new code path.

### D10. iOS "Delete all data" in one write transaction

A new `DataReset.deleteAll(db:)` in `DVMFinanceKit/Sources/DVMFinanceKit/Query/`
deletes the rows of each data table in the order of the foreign keys:
`rule_change_items`, `rule_change_reports`, `rule_conditions`,
`categorization_rules`, `transactions`, `budgets`, `snapshot_imports`,
`merge_reports`, and `export_state`. It returns the count of the deleted
transactions. `AppQueries.deleteAllData(appDatabase:)` runs it in one
`write` block, so an error rolls back everything. After the commit, the app
deletes the files in the snapshots folder and each database backup
(`<stem>.backup-<stamp>.sqlite`) that a snapshot import wrote. It does not touch the `MachineID`
marker file, so later snapshots keep the same machine identity.

A test lists the tables in `sqlite_master` and fails when a new data table is
not in the list of `DataReset`, or in an explicit list of kept tables (the
GRDB migration table). Thus a later migration cannot silently escape the reset.

`ImportView` adds a last `Section` with
`Button(role: .destructive) { Label("Delete all data", systemImage:
"exclamationmark.triangle.fill") }` in red. The button sets a flag that shows
`.confirmationDialog` (on iPad, `.alert` gives the same result) with the
warning text from the spec, a destructive "Delete all data" action, and
"Cancel". After the deletion, the view shows the count. The other tabs reload
when they appear, as they do after a snapshot import.

Alternative: delete the database file and create it again. This needs a close
and a reopen of the `DatabasePool` while views hold it. The row deletion keeps
the pool open and is atomic.

## Risks / Trade-offs

- [A rule reapplication on the web app changes the category of a sample row] →
  The sample rows are fictional, so a change does no harm. The removal finds
  them by id, not by category, so it still deletes them all.
- [The Swift and Python datasets drift apart] → The parity tests in both
  languages fix the same rows for the same `today`.
- [The user taps "Delete all data" by mistake] → The confirmation prompt has
  a "Cancel" action and tells the user to export a snapshot first.

- [The `NWConnection` probe adds about 2 seconds to a failed sync] → The probe
  runs only after a failure, never on the success path.
- [A new iOS version changes the `ECONNREFUSED` location in the user info] →
  The classifier then falls through to `.computerUnreachable`. That text also
  tells the user to make a new QR code. A unit test fixes each known shape of
  the user info.
- [The probe cannot run on the simulator with a real permission prompt] → The
  unit tests inject the probe. A manual check on a TestFlight build covers the
  three cases: permission off, an expired share, and a different network.
- [A bookmark to `/download` or `/upload` changes its page] → The 307 redirect
  keeps the bookmark working.
- [A user reloads after the QR icon and expects a new QR code] → The page
  removes `share=1`, so a reload shows the page only. The "Share to phone"
  button is still on the page.

## Migration Plan

No data migration. Deploy the web app and the iOS app independently. The web
redirects keep old links working. To roll back, revert the change. No stored
state depends on the new paths.
