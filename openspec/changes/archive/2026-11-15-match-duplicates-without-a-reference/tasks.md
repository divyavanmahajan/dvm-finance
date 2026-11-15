# Tasks

## 1. The second match key

- [x] 1.1 Add `normalize_text` beside `normalize_reference` in `core/dedup.py`,
  or reuse the one function for the IBAN and the remittance text. Verify with a
  test that `JYNQ VAN LCJFO ST` and `JYNQ VAN LCJFOST` give one value.
- [x] 1.2 Add `_counterparty_key`, which returns the account, the date, the
  amount, the normalized IBAN, and the normalized remittance text. Return None
  when the transaction holds a usable reference or no IBAN. Verify with a test
  for each of the three cases.
- [x] 1.3 Use the key in `check_duplicates`, inside the batch and against the
  database. The stored side reads the structured description of each row that
  holds no usable reference. Verify with a test that the labelled form of a
  stored transfer with `NOTPROVIDED` counts as a duplicate.
- [x] 1.4 Verify with a test that three payments of one day to one IBAN with
  three different remittance texts all import.
- [x] 1.5 Verify with a test that a row with a usable reference uses the
  reference key only, so that one row never matches two keys.

## 2. The rule of the statement file

- [x] 2.1 Hold the source file of each row of a group of the second key. Verify
  with a test that two rows of one file do not match each other.
- [x] 2.2 Verify with a test that two rows of two files do match.

## 3. The discovery and the refusal in the merge

- [x] 3.1 Group the live rows that hold no usable reference by the second key in
  `core/merge.py:preview_merge`. Verify with a test that a transfer pair with
  `NOTPROVIDED` gives one group.
- [x] 3.2 Refuse a group of the second key when one statement file gives more
  than one row. Add the reason. Verify with a test that the three-payment
  PayPal cluster is refused and that no row of it changes.
- [x] 3.3 Name the key of each group in `MergeGroup` and in `RefusedGroup`.
  Verify with a test that a reference group names the reference and a
  counterparty group names the IBAN and the remittance text.
- [x] 3.4 Show the key of each group in `web/templates/merge.html`. Verify with
  a client test that the page names both kinds of key.
- [x] 3.5 Verify with a test that a row never belongs to two groups.

## 4. The regression guard of the real data

- [x] 4.1 Add a test that builds the five clusters of a genuine repeated payment
  that the real database holds, and verify that the merge refuses each one.
- [x] 4.2 Add a test that the merge folds a transfer pair whose rows hold no
  remittance text, because 189 of the 214 real groups are of that shape.

## 5. The iOS port

- [x] 5.1 Port the second key to `Dedup.swift`, and the discovery and the
  refusal to `Merge.swift`. Verify with `xcodebuild test` on a Mac.
- [x] 5.2 Verify with a test that Swift refuses the same cluster as Python.

## 6. The documentation and the integration check

- [x] 6.1 Document the second key and the rule of the statement file in
  `docs/architecture.md` and `docs/product.md`.
- [x] 6.2 Run `pytest` and `ruff check .`, and verify that both pass with the
  coverage gate of 80 percent.
