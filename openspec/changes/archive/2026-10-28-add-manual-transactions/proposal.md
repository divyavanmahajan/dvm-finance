# Proposal

## Why

Every transaction in the database comes from a parsed file. The app offers no way
to record a payment that no statement reports. Cash spending is therefore
invisible, and the trends and the budgets describe only the money that moves
through a bank account. The user must be able to record a cash payment by hand,
and to correct or to remove the record later.

## What Changes

- The user can create a transaction by hand. The transaction holds a date, an
  amount, a description, and a category.
- Each hand-entered transaction belongs to one fixed pseudo account. The pseudo
  account holds no bank data, and no downloader writes to it.
- The id of a hand-entered transaction is a UUID. The id does not come from the
  content, so the user can correct the amount or the description, and the row
  keeps its identity.
- The category that the user types is a manual category. A rule reapplication
  therefore never replaces it. A tag-only rule can still add a tag.
- The user can edit and can flag a hand-entered transaction. A flag hides the
  row from each report. A flag does not delete the row.
- A purge removes each flagged row from the database. A purge is the only true
  deletion in the app. The system copies the database to a backup first.
- A snapshot export holds a flagged row, and a snapshot import copies the flag to
  the target machine. A purged row that returns from another machine therefore
  returns flagged, and it stays invisible.
- The user must categorize the withdrawal that funds the pseudo account as a
  transfer. The existing transfer exclusion then keeps the withdrawal out of the
  totals, and the cash rows carry the spending one time only.
- The phone offers the same functions. The user can create, edit, flag, and
  purge a hand-entered transaction on the phone, and the phone hides a flagged
  row. Both devices write to the same fixed pseudo account, and the two sets of
  rows merge without a conflict, because each row holds its own UUID.

## Capabilities

### New Capabilities

- `manual-transactions`: The creation, the edit, the flag, and the purge of a
  hand-entered transaction in the fixed pseudo account. This capability is the
  normative home for the exclusion of a flagged row. It names each surface that
  must hide a flagged row, and each surface that must still read one. Other
  capabilities inherit the rule, and they do not repeat it.
- `ios-manual-transactions`: The same functions on the phone, with the parity
  statements that the other iOS capabilities use. This capability is the
  normative home for the exclusion of a flagged row on the phone.

### Modified Capabilities

- `transaction-dedup`: The identity rule currently derives every id from the
  content of the transaction. A hand-entered transaction needs a UUID instead.
  The duplicate check must also never match a hand-entered row against an
  imported row.

The snapshot capabilities need no delta. `snapshot-export` already requires each
stored column of a transaction, so the two new columns travel without a change.
`snapshot-import` already requires the values of the snapshot to replace the
local values on an identity collision, so the flag reaches the target machine
without a change. `ios-snapshot-sync` already requires a round trip to lose no
exported field, so the phone needs no delta there either. Each new capability
states the two exceptions that protect this: an export never hides a flagged
row, and the duplicate check never hides one.

## Impact

- Schema: one Alembic migration adds two columns to `transactions`. The columns
  are the manual marker and the time of the flag. Both columns are nullable, so
  each existing row stays valid.
- Read paths: seven surfaces must hide a flagged row. The surfaces are the
  transactions list, the category trends, the cash flow, the budget actuals, the
  tag usage counts, the match count of each rule, and the rule preview. The
  transfer exclusion already binds the same seven surfaces, and it binds them
  with a separate SQL clause in each reader. This change adds one shared
  predicate instead, so a new reader cannot forget the flag in silence.
- New routes: the create form, the edit form, the flag action, the restore
  action, and the purge action.
- The phone: one GRDB migration adds the same two columns. The create screen,
  the edit screen, the flag action, and the purge action are new. The Swift work
  needs a Mac and the `xcodebuild test` gate.
- Unchanged: each parser, each downloader, the rule engine, and the snapshot
  format.
- Out of scope: the split of a downloaded transaction into parts, and the record
  of an expected future payment.
