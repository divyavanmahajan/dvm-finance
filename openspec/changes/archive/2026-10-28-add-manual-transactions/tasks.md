# Tasks

## 1. Schema

- [x] 1.1 Add the Alembic migration that creates `is_manual` (boolean, not null,
  default false) and `deleted_at` (timestamp, nullable, indexed) on
  `transactions`. Verify that `alembic upgrade head` and then `alembic downgrade
  -1` both run against a copy of a real database.
- [x] 1.2 Add the two columns to the `Transaction` model. Verify that the
  existing test suite still passes, and that each existing row reads as imported
  and live.

## 2. Identity and creation

- [x] 2.1 Add the creation function in `core/` that writes one hand-entered
  transaction with a UUID id, `is_manual` true, the account `CASH`, the typed
  category in `manual_category`, the typed tags in `manual_tags`, and a content
  hash. Verify with unit tests for the id form, for the manual fields, and for
  the stored hash.
- [x] 2.2 Add the edit function that changes the date, the amount, the
  description, the category, and the tags, keeps the id, recomputes the content
  hash, and stamps `updated_at`. Verify with a unit test that the id is equal
  before and after the edit.
- [x] 2.3 Reject a write to the account `CASH` from the import pipeline. Verify
  with a unit test that an import of a transaction for `CASH` is refused and
  that the database holds no new row.
- [x] 2.4 Add a unit test that two hand-entered rows with the same date, amount,
  and description both exist, and that an imported row never matches a
  hand-entered row in the duplicate check.

## 3. The flag and the shared exclusion

- [x] 3.1 Add the flag function and the restore function. Both refuse a row that
  is not hand-entered. Verify with unit tests for the accepted case and for the
  refused case.
- [x] 3.2 Add the shared `live_only` predicate beside the filter code, and
  compose it in `build_query`. Verify that the transactions list and its summary
  hold no flagged row.
- [x] 3.3 Compose the predicate in the category trends, the cash flow, and the
  budget actuals. Verify with a unit test for each one that a flagged row
  contributes nothing to a cell or a total.
- [x] 3.4 Compose the predicate in the tag usage counts, the match count of each
  rule, and the rule preview. Verify with a unit test for each one that a
  flagged row is not counted.
- [x] 3.5 Add a test that lists the seven readers and asserts that each one
  excludes a flagged row. Verify that the test fails when the predicate is
  removed from any one reader.
- [x] 3.6 Add a test that the snapshot export holds a flagged row with its flag,
  and that the duplicate check still treats the id of a flagged row as taken.

## 4. The snapshot round trip

- [x] 4.1 Add a round-trip test that exports a database with one flagged row,
  imports the file into a second database, and asserts that the row arrives with
  its flag and stays out of each total.
- [x] 4.2 Add a test for the return of a purged row: purge on the first
  database, import a snapshot from the second database, and assert that the row
  returns flagged and invisible.

## 5. Routes and pages

- [x] 5.1 Add the create route and the create form. The form requires a date, an
  amount, and a description, and it explains that the funding withdrawal belongs
  in a transfer category. Verify with client tests for the accepted form, for
  the missing amount, and for the amount of zero.
- [x] 5.2 Add the edit route and the edit form, and refuse the edit of an
  imported transaction. Verify with client tests for both cases.
- [x] 5.3 Add the flag route and the restore route, and refuse both for an
  imported transaction. Verify with client tests for both cases.
- [x] 5.4 Add the list of the flagged rows, so that the user can check them
  before the purge. Verify with a client test that it shows a flagged row and no
  live row.

## 6. The purge

- [x] 6.1 Add the purge function. It copies the database to a timestamped backup
  first, then it deletes each flagged row and no other row, and it returns the
  count. Verify with unit tests for the backup file, for the count, and for the
  empty case.
- [x] 6.2 Add the purge route with a confirmation step. Verify with a client
  test that the purge runs only after the confirmation.

## 7. Documentation

- [x] 7.1 Describe the pseudo account, the flag, and the purge in
  `docs/product.md`. Verify that the described user flow matches the routes.
- [x] 7.2 Describe the two new columns, the UUID identity, and the shared
  exclusion predicate in `docs/architecture.md`. Verify that the named modules
  exist.

## 8. The phone

- [x] 8.1 Add the GRDB migration that creates the same two columns in the local
  database. Verify that the migration runs against a database that an earlier
  version of the app wrote.
- [x] 8.2 Add the two fields to the Swift transaction model and to the snapshot
  model, and keep them through an import and an export. Verify with the existing
  round-trip test, extended with a flagged row.
- [x] 8.3 Add the creation of a hand-entered transaction with a UUID id, the
  account `CASH`, and the typed values in the manual fields. Verify with unit
  tests that name their Python origin, as the other ported units do.
- [x] 8.4 Add the edit of a hand-entered transaction. It keeps the id, stamps the
  row as updated, and refuses an imported row. Verify with unit tests for the
  equal id and for the refused case.
- [x] 8.5 Add the flag action and the restore action, and refuse both for an
  imported row. Verify with unit tests for both cases.
- [x] 8.6 Exclude a flagged row from the transactions list, the category trends,
  and the budget actuals, with one shared predicate as on the desktop. Verify
  with a unit test for each of the three readers.
- [x] 8.7 Add the purge with its database backup and its confirmation. Verify
  with unit tests for the backup file, for the count, and for the empty case.
- [x] 8.8 Add the create screen, the edit screen, the flag control, and the purge
  control to the transactions tab. Verify with `xcodegen generate && xcodebuild
  test` on a Mac.

## 9. Integration

- [x] 9.1 Add a Playwright flow that creates a hand-entered transaction, sees it
  in the list and in the cash flow, flags it, sees it disappear from both, and
  then purges it. Verify with `pytest -m e2e`.
- [x] 9.2 Add a cross-device check: create a hand-entered row on each side,
  merge the two snapshots, and verify that both rows exist and that a row
  flagged on one side is hidden on the other.
- [x] 9.3 Run `pytest` and `ruff check .`, and verify that the coverage gate of
  80 percent still passes.
