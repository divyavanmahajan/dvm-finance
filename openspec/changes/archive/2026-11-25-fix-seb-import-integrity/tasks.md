# Tasks

## 1. Currency check in the amount correction

- [x] 1.1 In `core/importer.py` `correct_amounts`, skip a row when the incoming `currency` is not the stored `currency` (design D3). Add a test in `tests/` for the scenario "The currencies are different" (stored -36.52 EUR, incoming -412.30 SEK, the amount stays). Verify that `pytest tests -k correct` passes.

## 2. Refuse the file without rates

- [x] 2.1 In `parsers/seb.py`, raise a parse error when a booking date has no rate, with a message that tells the user that the ECB rates are not available and to try again later (design D2). Remove the krona fallback. Add a test with an empty rate cache, and check that `import_file` raises `ImportError_` and writes no row. Verify with `pytest tests -k seb`.
- [x] 2.2 Make the same change in `parsers/ftfcu.py` for US dollars. Add the same test. Verify with `pytest tests -k ftfcu`.
- [x] 2.3 Check that the SEB and First Tech download jobs show the parse error as the job error. Verify with a test of the download job that patches the rate fetch to return no rates.
- [x] 2.4 Update `docs/product.md` (the SEB and First Tech import) for the new behavior without rates. Verify that the text uses ASD-STE100.

## 3. The SEB voucher key (Python)

- [x] 3.1 Add the shared fixture `tests/fixtures/seb_ids.json` with SEB rows and their expected ids. Include the values -412.3, 0.1, 1050.25, -11248, a missing balance, and the two -149 payments of 2026-10-19 (design D1, risk 1). Verify that the file is valid JSON.
- [x] 3.2 In `parsers/seb.py`, carry the krona amount and the krona balance on each parsed transaction. In `core/dedup.py` `generate_transaction_id`, build the SEB voucher key. Add a test that reads the fixture and checks each id. Verify with `pytest tests -k "seb or dedup"`.
- [x] 3.3 Add a test that parses an SEB file with 2 card payments under one voucher number and imports it. Check that the import stores 2 rows. Verify that the test passes.

## 4. Migration of the stored SEB ids (Python)

- [x] 4.1 Add the Alembic migration after `e4b7d2a91c36` (design D4). It copies the database file to `abn_combined.db.before-seb-ids-<timestamp>`, then changes `transactions.id`, `transactions.merged_into`, and `rule_change_items.transaction_id` in one transaction. Add `downgrade`, which refuses when two rows share one voucher number. Verify with a migration test that seeds old SEB rows with a manual category and a rule change item, upgrades, and checks the new ids, the manual category, and the references.
- [x] 4.2 Add a test for the scenario "The user imports the latest SEB file after the migration": seed rows with old ids, upgrade, import a file that holds them and new rows, and check the counts of new and duplicate rows. Verify that the test passes.
- [x] 4.3 Update `docs/architecture.md` (transaction identity and the SEB id). Verify that the text uses ASD-STE100.

## 5. Old SEB ids in a snapshot (Python)

- [x] 5.1 In `core/snapshots.py`, change each incoming SEB id in the old form to the new form before the merge, with one map for the references (design D5). Add a test that imports a snapshot with an old SEB id into a database with the new id, and checks that the import adds no second row. Verify with `pytest tests -k snapshot`.

## 6. iOS parity

- [x] 6.1 In `DVMFinanceKit` `SEBParser.swift`, throw an error when a booking date has no rate, and carry the krona amount and the krona balance. In `TransactionID.swift`, build the SEB voucher key. Add the fixture from 3.1 to `TransactionIDTests` and check each id. Verify with `swift test` in `ios/DVMFinanceKit`.
- [x] 6.2 Show the parser error on the import screen with the message of design D2. Verify with a unit test of the import pipeline that uses an empty rate cache and checks that no row is written.
- [x] 6.3 Add the GRDB migration `v7` in `AppDatabase.swift` (design D6). Verify with a test that seeds old SEB rows with a manual category and a rule change item, runs the migrator, and checks the new ids.
- [x] 6.4 Change old SEB ids in an incoming snapshot on iOS (design D5). Verify with a snapshot merge test.
- [x] 6.5 Verify that `xcodegen generate && xcodebuild test -scheme DVMFinance` passes.

## 7. Integration checks

- [x] 7.1 Verify that `pytest`, `ruff check .`, and `pytest --cov=abn_combined` (80% gate) pass.
- [x] 7.2 On a copy of the real database, run the migration and import `seb-50110466225-2026-11-22.csv`. Verify that the database then holds 182 SEB rows, each in EUR, and that each amount equals `native_amount / eur_rate_used`, rounded to 2 places.

## Workflow follow-up

- Run the migration on the real database, and import the latest SEB file.
- Export a snapshot and sync it to the iPhone.
- Archive the change after the review and the merge.
