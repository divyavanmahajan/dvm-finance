# Tasks

## 1. The shared SEPA type table

- [x] 1.1 Add a helper in `parsers/description.py` that maps the Dutch SEPA text
  to `sepa_type`, `transaction_type`, `direct_debit_type`, and `recurring`.
  Verify with a unit test that `SEPA INCASSO ALGEMEEN DOORLOPEND` gives
  `SEPA Direct Debit`, `INCASSO`, `General`, and true.
- [x] 1.2 Call the helper from `parse_sepa_description`, and verify that each
  present test in `tests/test_parsers.py` still passes.

## 2. The tagged parser

- [x] 2.1 Map `/CSID/` to `creditor_identifier` and `/MARF/` to
  `mandate_reference` in `parse_mt940_description`. Verify with a unit test that
  `other_fields` holds neither tag.
- [x] 2.2 Call the shared helper for a `/TRTP/` value that starts with `SEPA`,
  and report the format `sepa`. Verify with a unit test that a tagged `IDEAL`
  value keeps the format `mt940`.
- [x] 2.3 Select the Tikkie branch in `parse_tikkie_fields` by `sepa_type`.
  Verify with a unit test that a tagged `/TRTP/SEPA OVERBOEKING` description
  with a `TIKKIE ID` remittance text still gives `tikkie_id`, `payer_name`, and
  `payer_iban`.
- [x] 2.4 Add a unit test that parses the tagged form and the labelled form of
  the same LEBARA direct debit. Verify that the two structured descriptions hold
  the same value for each canonical key.

## 3. The labelled parser

- [x] 3.1 Rename the `OMSCHRIJVING:` key from `description` to
  `remittance_info`, and the `KENMERK:` key from `reference` to
  `end_to_end_reference`. Verify with a unit test that the old keys are absent.
- [x] 3.2 Update each reader of the old keys in `parse_sepa_description`,
  including the Tikkie branch that reads the `KENMERK:` timestamp. Verify that
  `pytest tests/test_parsers.py` passes.
- [x] 3.3 Update `docs/architecture.md` and `docs/product.md` where they name
  the old keys. Verify that no document names a structured `description` key or
  a structured `reference` key.

## 4. The column and the migration

- [x] 4.1 Add the column `end_to_end_reference` with an index to `Transaction`
  in `core/models.py`. Verify that `pytest tests/test_models.py` passes.
- [x] 4.2 Add the column `merged_into` to `Transaction`, with an index. Verify
  that `pytest tests/test_models.py` passes.
- [x] 4.3 Write one Alembic migration for both new columns and their indexes.
  Verify with `pytest tests/test_migrations.py` that the upgrade and the
  downgrade both run.
- [x] 4.4 Backfill the column from `description_structured`, for the old key
  `reference` and for the new key `end_to_end_reference`. Verify with a test
  that a row from before the change holds its reference after the upgrade.
- [x] 4.5 Add the one-time pass that rewrites the stored
  `description_structured` of each SEPA row with the new parser. Select a row
  whose stored format is `sepa`, and also a row whose stored format is `mt940`
  with a `transaction_type` that starts with `SEPA`. Verify with a test that a
  stored tagged row holds `creditor_identifier` after the pass, and that a
  stored `pos` row does not change.

## 5. The duplicate check

- [x] 5.1 Store the reference in the new column in `insert_transactions`. Verify
  with a test that a point-of-sale row holds an empty value.
- [x] 5.2 Match the account with the reference in `check_duplicates`, inside the
  batch and against the database. Verify with a test that the labelled form of a
  stored tagged payment counts as a duplicate.
- [x] 5.3 Ignore an empty reference, the value `NONREF`, and the value
  `NOTPROVIDED`, and remove each whitespace character before the comparison.
  `tests/fixtures/mt940_sample.STA` holds `NOTPROVIDED` 136 times and
  `NOTP ROVIDED` three times. Also keep a payment apart from its reversal: the
  same file holds three pairs that share one reference with the opposite sign,
  so the amount belongs to the match key. Verify with a test that the reference
  check adds no duplicate across that whole file. Do not assert a total
  duplicate count for it: the file holds 19 duplicates of the id, which is
  older behavior than the reference check.
- [x] 5.4 Add a test that `generate_transaction_id` gives the same id as before
  this change, for a SEPA transaction and for a point-of-sale transaction.
- [x] 5.5 Derive the column on the snapshot-import path when the snapshot holds
  no value for it. Verify with a test that a snapshot without the field gives a
  row that holds the reference from its structured description.
- [x] 5.6 Add a test that a statement import counts a payment as a duplicate
  when a snapshot already supplied that payment.
- [x] 5.7 Add a test that the snapshot import writes a row whose reference
  matches a stored row with another id. The snapshot import stays the only path
  that may replace a row.

## 6. The rule migration

- [x] 6.1 Add the one-time migration of the field target of a rule. Rename
  `reference` to `end_to_end_reference` on each rule and on each extra
  condition. Rename `description` to `remittance_info` on a rule of the type
  `structured_field` only. Do not rename `description` on an extra condition:
  `_evaluate_single_condition` reads that target from the raw text for each rule
  type, so a rename there would change the behavior. Verify with a test that a
  `full_description` rule and an extra condition on `description` both stay as
  they are.
- [x] 6.2 Run the migration through `record_rule_change`, and verify with a test
  that the system stores a report with the rule before and after the change.
- [x] 6.3 Verify with a test that a transaction with a manual category keeps its
  category after the migration.

## 7. The scope of the purge and of the flagged list

- [x] 7.1 Exclude a row that holds a value in `merged_into` from
  `purge_flagged_transactions`. Verify with a test that a purge with one row of
  the user and one merged row deletes one row and reports the number one.
- [x] 7.2 Exclude a merged row from `_flagged_rows` in `api/manual.py`. Verify
  with a client test that the list of the flagged transactions does not hold a
  merged row.
- [x] 7.3 Do this group before group 8, so that no merge can write a row that
  the purge would delete. Verify with the two tests above.

## 8. The merge of the stored duplicates

- [x] 8.1 Add `core/merge.py` with the discovery of each group. Group each live
  row of one account by its end-to-end reference, and ignore an empty value and
  `NONREF`. Verify with a test that two accounts with one shared reference give
  no group.
- [x] 8.2 Pick the survivor by the lowest id in the lexicographic order. Verify
  with a test that the choice does not depend on the order of the rows of the
  input.
- [x] 8.3 Refuse a group whose rows hold two different manual categories, and
  report it. Verify with a test that the system changes no row of such a group.
- [x] 8.4 Carry the manual category and the manual tags to a survivor that holds
  none. Verify with a test that the merge does not overwrite a value that the
  survivor already holds.
- [x] 8.5 Write `deleted_at` and `merged_into` on each other row. Verify with a
  test that the transactions list and the cash flow each hold the survivor one
  time.
- [x] 8.6 Store the report of the merge. Verify with a test that the report
  names each survivor, each flagged row, each carried value, and each refused
  group.
- [x] 8.7 Add the undo of a merge. Clear `deleted_at` and `merged_into`, and
  keep each carried manual categorization. Verify with a test that the two rows
  appear again in the transactions list.
- [x] 8.8 Add the route of the preview, the route of the merge, and the route of
  the undo. Verify with a client test that the preview changes no row, and that
  the merge needs the confirmation of the user.
- [x] 8.9 Document the merge in `docs/product.md` and in `docs/architecture.md`.
  Verify that each document names the two kinds of flag.

## 9. The normalization of the reference

- [x] 9.1 Add `normalize_reference` to `core/dedup.py`. Remove each whitespace
  character, each period, and each hyphen, then change the text to upper case.
  Verify with a test that `8022.7644 .9692.6345` and `8022764496926345` give one
  value.
- [x] 9.2 Use the normalized form for the sentinel test, for the match key, and
  for each stored value that `check_duplicates` reads. Keep the original text in
  the column. Verify with a test that the stored row holds the separators and
  that the other form still matches it.
- [x] 9.3 Use the normalized form in the group key of `core/merge.py`, and
  report the original text of the first row. Verify with a test that the group
  names what the bank wrote.
- [x] 9.4 Verify with a test that the amount still keeps a payment apart from
  its reversal when the two references differ only by a separator.

## 10. The iOS port

- [x] 10.1 Port the parser changes to `ios/DVMFinanceKit`, and name the Python
  origin of each ported unit. Verify with `xcodebuild test` on a Mac.
- [x] 10.2 Port the two columns, the GRDB migration, and the duplicate check.
  Verify with a test that a snapshot from the Python app merges without a second
  row.
- [x] 10.3 Port the discovery of a group and the choice of the survivor. Verify
  with a test that Swift picks the same survivor as Python for one group.
- [x] 10.4 Port the two one-time passes of `core/restructure.py`. The iOS app
  imports a statement and applies the rules on its own, so a row and a rule
  that it wrote before this change need the same rewrite. Verify with a test
  that a stored tagged row holds `creditor_identifier` after the pass, and that
  a rule on `reference` holds `end_to_end_reference`.
- [x] 10.5 Verify with a test that the amount key of Swift gives the same string
  as `core/dedup.py:_amount_key` for each of seven amounts. The key decides
  which rows form a group, so a divergence would make the two apps merge
  different sets.

- [x] 10.6 Port `normalize_reference` to `Dedup.swift`, and use it in the
  sentinel test, the match key, and the group key of `Merge.swift`. Verify with
  a test that the two spellings of four real references agree.

## 11. The integration check

- [x] 11.1 Import a statement in the tagged form and then the same payment in the
  labelled form through the web interface. Verify in a real browser that the
  import report counts one duplicate, and that the transaction list holds one
  row.
- [x] 11.2 Open the preview of the merge in a real browser on a database that
  holds a duplicate pair. Confirm the merge, and verify that the transactions
  list holds one row and that the report names the pair.
  Done in headless Chromium (Playwright), because the Chrome extension is not
  connected. Two made-up statements held one payment in the tagged form and in
  the labelled form: the second import counted one duplicate, and the list held
  one row. A database seeded with a duplicate pair showed the group in the
  preview. The unconfirmed merge changed nothing. The confirmed merge folded
  one row, the list went from two rows to one, and the report named the row
  that stayed and the flagged row.
- [x] 11.3 Run `pytest` and `ruff check .`, and verify that both pass with the
  coverage gate of 80 percent.
