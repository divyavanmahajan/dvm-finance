# Design

## Context

See `proposal.md` - Why. Three properties of the current code shape this design.

The id of a transaction comes from its content, in `core/dedup.py`. The id holds
the account, the date, the amount, and a hash of the description. An edit of any
of those values therefore produces a different row.

A transaction is immutable after the import, except for the category fields and
the tag fields. The application offers no route that creates, edits, or deletes
a transaction.

Seven surfaces read the transactions, and they do not share one query builder.
`core/filters.py` holds `build_query` for the list. `core/trends.py`,
`core/cash_flow.py`, and `core/budget_report.py` each build their own aggregate
query against the table. The transfer exclusion already binds the same seven
surfaces, and it binds them with a separate SQL clause in each reader. Those
clauses have already drifted in form: `core/filters.py` uses `ilike` with an
explicit empty-category case, and `core/cash_flow.py` uses `like` without it.
The two agree in behavior on SQLite today. The drift shows how a second
duplicated clause would end.

## Goals / Non-Goals

**Goals:**

- Give a hand-entered row an identity that survives an edit.
- Make the removal of a row safe across two machines, with the existing snapshot
  merge rules and with no new field in the snapshot header.
- Add the exclusion of a flagged row one time, not seven times.

**Non-Goals:**

- A second pseudo account, or a pseudo account that the user names. See the
  risks below for the reason.
- An audit record for the edit of a transaction. The rule changes have
  `record_rule_change`; a transaction edit gets no equivalent in this change.
- A report of the difference between the cash balance and the counted cash.

## Decisions

### A UUID id for a hand-entered row, and a marker column beside it

A content-derived id makes an edit impossible: the corrected row is a new row,
and the old row stays behind. A UUID id separates the identity from the values.

The system also needs to know which rows are hand-entered, because only those
rows accept an edit and a flag. Three options exist. An id prefix such as
`manual_` needs no column, but it turns an identity into a string to parse. The
pseudo account answers the question today, but it stops working on the day a
hand-entered correction belongs in a real bank account. An explicit column says
exactly one thing, it is indexable, and it survives both changes.

**Decision**: add `is_manual` as a boolean column, and give a hand-entered row a
UUID id.

### The UUID makes the phone a first-class writer

The phone and the computer can both create a cash row while neither can see the
other. A content-derived id would make this dangerous in two ways. Two devices
that record the same payment would produce the same id, so the merge would drop
one row and the user would lose a record. Two devices that record different
payments with the same date, amount, and description would also collide.

A UUID removes both cases. Each device mints its own ids, a collision is not
possible, and the merge is a union. The fixed pseudo account needs no device
column and no name per device, because the rows never compete for an id.

**Decision**: both devices create hand-entered rows in the same `CASH` account.
The phone uses the same UUID rule and the same two columns. No field records
which device wrote a row; the snapshot already records the machine that
exported it.

### `deleted_at` as a timestamp, not a boolean

A boolean answers "is it flagged". A timestamp answers "since when", at the same
cost in the schema and in the queries. The timestamp also allows a later purge
by age without a second migration.

**Decision**: add `deleted_at` as a nullable timestamp. `NULL` means live.

### One shared predicate for the seven surfaces

The transfer exclusion shows the cost of the alternative. Each reader holds its
own clause, the clauses have drifted in form, and the `is_transfer_category`
helper is now imported but unused in three modules.

A missed reader does not fail loudly. It returns a total that silently holds a
removed row.

**Decision**: add one predicate, for example `live_only(query)`, in
`core/filters.py` beside the existing filter code. Each of the seven readers
composes it. A test lists the readers and asserts that each one excludes a
flagged row. The transfer exclusion keeps its own clauses; this change does not
refactor it.

### The flag travels on the existing merge rules

`snapshot-export` already requires each stored column of a transaction, so
`is_manual` and `deleted_at` travel with no change to the format or the schema
version. `snapshot-import` already requires the values of the snapshot to
replace the local values on an identity collision, so the flag reaches the
target machine with no change.

This gives a useful property for free. A machine purges a row. A second machine
still holds the row with its flag. The next snapshot returns the row to the
first machine, and the row returns flagged. It therefore stays out of each list
and each total. A purge needs no tombstone, and a resurrection is harmless.

**Decision**: change no snapshot capability, on either device. State the two
exceptions in each new capability instead: the export never hides a flagged row,
and the duplicate check never hides one.

### The typed category is a manual category

A hand-entered row has no description that a rule was written for, and the user
already knows the category when they type the row. The manual fields protect it,
and that matches the project rule that a rule reapplication never replaces a
manual categorization. A tag-only rule still adds a tag, because a tag-only rule
already applies to a manually categorized row.

### The purge borrows the backup of the snapshot import

The snapshot import already copies the database to a timestamped backup before
it changes anything. The purge is the only other irreversible operation in the
application. It reuses the same helper rather than a new one.

## Risks / Trade-offs

- **A missed reader keeps a removed row inside a total** -> One shared predicate,
  plus a test that walks the seven readers. The failure is silent, so the test
  is the control, not the review.
- **A user-named pseudo account would break the identity story** -> The pseudo
  account stays fixed. A named account invites a hand-kept copy of a real bank
  account. A statement for that account can arrive later through a CSV or a
  snapshot, the description of the hand-typed row never matches, and the total
  counts the payment twice. A fixed cash account cannot reach that state,
  because no statement is ever written for it.
- **A flag and a restore on two machines resolve by the order of the imports** ->
  Accepted, and stated as a limitation. The merge replaces the local values with
  the values of the snapshot, and it does not compare `updated_at`. The user is
  one person, and the window is small.
- **The user forgets to categorize the funding withdrawal as a transfer** -> The
  create form says so. The totals are otherwise too high by the amount of each
  withdrawal, and nothing reports an error.
- **The phone and the computer edit the same row between two syncs** -> Accepted,
  with the same limitation as above: the later import wins. The risk is small,
  because a hand-entered row is usually edited on the device that created it.
- **The phone must ship the exclusion with the feature** -> The phone needs the
  exclusion rule in the same release as the create screen. A phone that creates
  rows but ignores the flag shows a row that the user removed on the computer.
  The Swift work needs a Mac and the `xcodebuild test` gate, so plan it beside
  the Python work rather than after it.

## Migration Plan

1. One Alembic migration adds `is_manual` (boolean, default false, not null) and
   `deleted_at` (timestamp, nullable) to `transactions`, with an index on
   `deleted_at`. Each existing row reads as imported and live.
2. The migration adds no row and removes no row. A rollback drops the two
   columns. A rollback after a purge cannot return the purged rows; the backup
   of the purge holds them.
3. One GRDB migration adds the same two columns to the local database of the
   phone. The phone needs no data migration, because each existing row reads as
   imported and live.
4. The snapshot schema version stays 1. An older application that reads a newer
   snapshot ignores the two fields, and it therefore shows a flagged row. State
   this in the release note.

## Open Questions

- Where the purge belongs in the user interface, and whether it also offers a
  purge of the rows that the user flagged before a date. The specification
  requires the purge of each flagged row; a filter by age is an addition that
  needs no change to the specification.
- Whether the user interface shows the pseudo account as `CASH` or as a friendly
  label. The reserved identifier stays `CASH` in the database either way.
