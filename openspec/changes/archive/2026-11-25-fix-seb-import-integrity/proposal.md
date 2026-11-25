# Proposal

## Why

On 2026-11-22, an SEB download replaced the euro amount of all 89 stored SEB
transactions with the krona amount. The parser did not get the ECB rates, so it
gave krona amounts. The amount correction then wrote these amounts over the
euro rows, and the currency stayed EUR.

The scan of the real data also found a second fault. SEB gives one voucher
number to many card payments. The SEB files hold 182 transactions, but the
database holds only 89, one for each voucher number. The import treats the
other 93 transactions as duplicates and does not store them.

The user restored the 89 euro amounts by hand from a backup. The next SEB import
can cause the same damage, so the fix is necessary now.

## What Changes

- The amount correction SHALL NOT replace a stored amount when the incoming
  currency is not the stored currency. The import counts that transaction as a
  duplicate.
- The SEB and First Tech parsers SHALL refuse the file when they cannot get the
  ECB rates. They do not store krona or US dollar amounts any more. The import
  writes no row and tells the user to try again later. **BREAKING** for the
  behavior without rates: before, the parsers stored the native currency.
- **BREAKING** The id of an SEB transaction SHALL hold the voucher number, the
  booking date, the krona amount, and the krona balance. Two card payments with
  one voucher number then get two ids.
- An Alembic migration on the web and a GRDB migration on iOS SHALL change the
  id of each stored SEB transaction to the new form. The migrations keep the
  manual category, the manual tags, and the references from the audit trail.
- The snapshot import SHALL change an incoming SEB id in the old form to the
  new form. A snapshot from an app version before this change then merges
  without a second row.
- After the migration, the user imports the latest SEB file again. The import
  adds the 93 missing transactions and counts the 89 known transactions as
  duplicates.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transaction-dedup`: the SEB part of "Deterministic transaction identity"
  changes. A new requirement changes the id of each stored SEB transaction.
- `statement-parsers`: the SEB and First Tech conversion requirements refuse
  the file without rates. The SEB provider identifier holds the new fields.
- `statement-upload`: the amount correction compares the currency first.
- `snapshot-import`: a new requirement changes an old SEB id in a snapshot to
  the new form.
- `ios-statement-import`: the iOS SEB parser refuses the file without rates,
  and the iOS id of an SEB transaction has the new form.

## Impact

- Python: `core/dedup.py` (`generate_transaction_id`), `core/importer.py`
  (`correct_amounts`), `parsers/seb.py`, `parsers/ftfcu.py`, `parsers/fx.py`,
  `core/snapshots.py`, and a new Alembic migration after `e4b7d2a91c36`.
- Swift: `DVMFinanceKit` `TransactionID.swift`, `SEBParser.swift`,
  `SnapshotCodec.swift` or the snapshot merge, and a GRDB migration `v7` in
  `AppDatabase.swift`.
- Data: the migration changes the 89 SEB ids in the web database and in the iOS
  database. The tables `transactions` (`id`, `merged_into`) and
  `rule_change_items` (`transaction_id`) hold these ids.
- Tests: the shared id fixtures (`TransactionIDTests`, the parser fixtures) get
  new SEB cases.
- Docs: `docs/architecture.md` (transaction identity) and `docs/product.md`
  (the SEB import).
