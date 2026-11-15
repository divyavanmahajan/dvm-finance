# Proposal

## Why

ABN AMRO writes the same SEPA payment in two description forms. The tagged form
uses slash tags such as `/TRTP/` and `/EREF/`. The labelled form uses Dutch
labels such as `INCASSANT:` and `KENMERK:`. The two parsers give the same
payment different structured keys and a different raw text. A rule that matches
one form therefore misses the other, and the duplicate check keeps both rows.

The example below is one payment in both forms. The two forms also disagree on
the remittance text, because the labelled form holds a line-break space:
`LEBARA NL-039442543-277` against `LEBARA NL-03944254 3-277`. No check on the
description can join them.

## What Changes

- The tagged parser SHALL map `/CSID/` to `creditor_identifier` and `/MARF/` to
  `mandate_reference`. Today it hides both values in `other_fields`.
- The tagged parser SHALL report the format `sepa`, and not `mt940`, when the
  `/TRTP/` value starts with `SEPA`. A tagged `IDEAL` value keeps the format
  `mt940`.
- The tagged parser SHALL give the same normalized `transaction_type` as the
  labelled parser. `SEPA INCASSO ALGEMEEN DOORLOPEND` becomes
  `SEPA Direct Debit`. The parser SHALL also add `sepa_type`,
  `direct_debit_type`, and `recurring`.
- **BREAKING** The labelled parser SHALL rename its remittance key from
  `description` to `remittance_info`, and its `KENMERK:` key from `reference`
  to `end_to_end_reference`. The tagged names become the canonical names.
- The system SHALL store the end-to-end reference in a new indexed column.
- The duplicate check SHALL treat two transactions of the same account as
  duplicates when they hold the same end-to-end reference.
- The system SHALL migrate each existing rule that targets a renamed key, and
  SHALL write a rule change report.
- The Tikkie extraction SHALL select its branch by `sepa_type`, and not by the
  raw Dutch `transaction_type`. The normalization breaks the present test
  without this change.
- The system SHALL merge each pair of rows that the database already holds for
  one payment. The merge keeps one row, carries the manual categorization to it,
  and flags each other row. A new column `merged_into` names the row that
  absorbed the flagged row.
- **BREAKING** The purge and the list of the flagged transactions SHALL exclude
  a merged row. Today the purge deletes each row that holds a flag, and it reads
  no other field. It would therefore delete a merged row, free its id, and let
  the next import write the duplicate again.

## Capabilities

### New Capabilities

- `transaction-merge`: the system finds each group of rows that report one
  payment, merges the group to one row, and reports the result. The user can
  also undo a merge.

### Modified Capabilities

- `statement-parsers`: the structured description of the two SEPA forms uses one
  set of keys, one format value, and one normalized transaction type.
- `transaction-dedup`: the duplicate check adds the end-to-end reference as a
  second match key, beside the transaction id.
- `categorization-rules`: the system migrates the field target of a rule that
  names a renamed structured key.
- `manual-transactions`: the purge and the list of the flagged transactions
  exclude a merged row. The flag of a merged row is not a removal flag of the
  user.

## Impact

- `src/abn_combined/parsers/description.py`: `parse_mt940_description`,
  `parse_sepa_description`, and `parse_tikkie_fields`.
- `src/abn_combined/core/dedup.py`: `check_duplicates` and
  `insert_transactions`.
- `src/abn_combined/core/models.py`: a new `end_to_end_reference` column, with
  an Alembic migration and a backfill from `description_structured`.
- `src/abn_combined/core/categorizer.py`: the one-time migration of the field
  target of a rule, through `record_rule_change`.
- The iOS companion mirrors the parser and the dedup logic. The change needs the
  same port in `ios/DVMFinanceKit`, so that a snapshot still merges without a
  heuristic.
- The transaction ids do not change. Each already imported row keeps its id, so
  each manual categorization survives.
- The snapshot import does not use the duplicate check. It stays the only path
  that may replace a row, by explicit user action.
- `src/abn_combined/core/manual_txn.py` and `src/abn_combined/api/manual.py`:
  `purge_flagged_transactions` and `_flagged_rows` both read `deleted_at` alone.
  Each one needs the exclusion of a merged row.
- A new core module and a new route for the merge. The merge needs a preview, a
  report, and an undo.
- The merge changes each total, because `live_only` hides a flagged row from the
  seven readers. No reader needs a change.
