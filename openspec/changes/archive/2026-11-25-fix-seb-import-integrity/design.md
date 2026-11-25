# Design

## Context

See proposal.md - Why. These facts from the real data shape the approach:

- 14 SEB files hold 182 different transactions from 2026-05-25 to 2026-11-20.
  They hold only 89 different voucher numbers. The voucher number `5400000001`
  covers most card payments.
- The key (voucher number, booking date, krona amount, krona balance) gives 182
  different values. Each row has the same balance and value date in each
  export that holds it. The key (voucher number, booking date, krona amount)
  gives only 180 values, because two equal payments of -149 krona fall on one
  day.
- Each stored SEB row keeps `voucher_number`, `native_amount`, and
  `native_balance` in `description_structured`. These values belong to the
  transaction that the row holds. The migration can therefore compute the new
  id without the statement files.
- `correct_amounts` in `core/importer.py` writes only `amount`,
  `transaction_hash`, and `updated_at`. It does not compare the currency.
- The ids are part of the snapshot format, and the two apps must give the same
  id for one transaction.

## Goals / Non-Goals

**Goals:**

- No import can write an amount in one currency over a stored amount in a
  different currency.
- Each SEB transaction gets its own id, in both apps.
- The migration keeps each manual category, each manual tag, and the audit
  trail.

**Non-Goals:**

- An automatic import of the 93 missing transactions in the migration. The
  migration does not read files or use the network. The user imports the
  latest SEB file after the update.
- A change to the Wise and PayPal fallback without rates. These parsers convert
  most rows without the ECB feed. The currency check in the correction protects
  their stored rows.
- A local cache of the ECB rates.

## Decisions

### D1. The SEB id holds the voucher, the date, the krona amount, and the balance

Format: `<account>_<voucher>_<YYYY-MM-DD>_<amount>_<balance>`, for example
`seb:divyavanmahajan_5400000001_2026-10-02_-412.30_1234.56`. Each krona value
has exactly 2 decimal places. The code rounds the exact decimal half up. The
Python code uses `Decimal(str(value)).quantize(Decimal("0.01"))`, and the Swift
code uses `Decimal` with `.plain` rounding. A shared fixture fixes the text for
the two apps.

- The id uses the krona values, not the euro values. A new ECB rate or a
  rounding change then does not change the id.
- Alternative: a hash of the full CSV row. A hash is not readable, and a change
  to the text column of SEB would change each id. Rejected.
- Alternative: the voucher number and the line number in the file. Each export
  has a different window, so the line number changes. Rejected.
- Alternative: the date, the amount, and the balance without the voucher. This
  also gives 182 values, but the voucher keeps the id readable and matches the
  old prefix. Rejected.

### D2. The SEB and First Tech parsers refuse the file without rates

Each row of these files is in a currency that is not the euro. A file that
stores krona or US dollar rows makes each total wrong, and the old fallback
also caused the damage of 2026-11-22. The parser raises a parse error with a
clear message. `import_file` already changes a parse error into an
`ImportError_` and writes no row. The download job shows the same message.

- Alternative: store the rows in the native currency, and mark them for a later
  conversion. That needs a new column and a new job. Rejected for this change.

### D3. The correction compares the currency first

`correct_amounts` skips a row when the incoming `currency` is not the stored
`currency`. The import then counts the row as a duplicate. This check protects
the Wise and PayPal rows too (see Non-Goals).

### D4. The migration computes the new id from the stored row

The Alembic migration (after `e4b7d2a91c36`) selects each row with
`accountNumber LIKE 'seb:%'` and an id without a date part. It computes the new
id from `description_structured` and `transactiondate`. In one transaction it
updates `transactions.id`, `transactions.merged_into`, and
`rule_change_items.transaction_id`. A row without `voucher_number` or
`native_amount` keeps its id, and the migration logs it. The real data has no
such row.

The function that computes the id lives in `core/dedup.py`. The migration
copies the formatting code inline, because an Alembic migration must not
import application code that can change later.

The `downgrade` changes each id back to `<account>_<voucher>`. It refuses when
two rows share one voucher number, because the old form cannot hold them.

### D5. The snapshot import changes an old SEB id

The snapshot import checks each incoming transaction. An SEB id with only the
account and the voucher number gets the new id from the incoming structured
description. The import changes the references in the snapshot with one map
before the merge. The export always writes the new form.

### D6. iOS parity

`TransactionID.swift` gets the same key, and `SEBParser.swift` carries the
krona amount and balance on the parsed transaction. `SEBParser` throws an error
when the rate cache has no rate for a booking date. The GRDB migration `v7`
does the same work as D4. The snapshot merge on iOS does the same work as D5.

## Risks / Trade-offs

- [The Python and Swift code format a krona value in different ways] → A shared
  fixture holds rows with values such as -412.3, 0.1, 1050.25, and -11248, and
  the two test suites check the exact id text.
- [SEB changes the balance of a booked row in a later export] → The data shows
  no such case in 14 exports. If it happens, the import adds a second row. The
  user can merge the two rows with the duplicate merge.
- [A user imports an old snapshot after the migration] → D5 changes the old ids
  before the merge.
- [The ECB feed is down for a long time] → The user cannot import an SEB or a
  First Tech file during that time. The message tells the user to try again
  later. The stored data stays correct.

## Migration Plan

1. The app has no automatic backup before a schema upgrade. The migration
   therefore copies the database file to
   `abn_combined.db.before-seb-ids-<timestamp>` before it changes a row, when
   at least one SEB row has an old id.
2. The Alembic migration changes the SEB ids. The iOS migration `v7` runs at
   the first start of the new app version.
3. The user imports the latest SEB file on the web. The file of 2026-11-22
   holds all 182 transactions. The import adds 93 rows.
4. The user exports a snapshot and syncs it to the iPhone.
5. Rollback: restore the backup from step 1. The `downgrade` works only before
   step 3.
