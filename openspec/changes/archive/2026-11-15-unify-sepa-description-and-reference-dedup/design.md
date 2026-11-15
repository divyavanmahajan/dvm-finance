# Design

## Context

See proposal.md for the motivation. See the spec deltas for the requirements.

`parse_transaction_description` tries the tagged parser first. The tagged
pattern needs a `/TAG/` form, so a labelled description never reaches the tagged
parser. The two parsers are therefore independent, and each one owns its own key
names today.

The duplicate check uses `generate_transaction_id`. For a bank transaction the
id joins the account, the date, the amount, and an MD5 hash of the raw
description. The two description forms of one payment hold a different raw text,
so the two ids differ. The labelled form of the example holds a line-break space
inside the remittance text. For this reason no hash of the description can join
the two forms.

The rules read the structured description by the key name. `_check_primary_condition`
and `_evaluate_single_condition` look the field target up in the structured
dictionary. An unknown field target matches nothing. A rename of a key therefore
changes the behavior of a stored rule.

`parse_tikkie_fields` selects its branch by the raw text of `transaction_type`.
It compares against `SEPA OVERBOEKING` and `IDEAL`.

## Goals / Non-Goals

**Goals:**

- Give one payment the same structured keys in both description forms.
- Detect the second form of one payment as a duplicate.
- Keep each transaction id stable, so that each manual categorization survives.
- Keep the Tikkie extraction of the tagged form.

**Non-Goals:**

- No change to the `:61:` parse, to the balances, or to the date fields of the
  MT940 parser. They need their own change.
- No new user interface. The import report already counts the duplicates.
- No merge of two rows that hold two different manual categories. The system
  refuses such a group, and the user decides.
- No automatic merge at the import. The user opens the preview and confirms.

## Decisions

### The tagged key names are the canonical names

The tagged form follows the SEPA field names, so `remittance_info` and
`end_to_end_reference` describe the content better than `description` and
`reference`. The labelled parser therefore renames its two keys.

The rename of `description` is free. A rule with the field target `description`
never reads the structured dictionary, because both match functions
short-circuit to the raw text. The structured `description` key is unreachable
for a rule today.

The rename of `reference` is not free. A `structured_field` rule can name it.
The migration therefore renames the field target of such a rule.

Alternative: keep both keys as aliases. Rejected. The style rule of the project
gives each meaning one word, and two keys for one value make a rule ambiguous.

### Share one SEPA type table between the two parsers

A single helper maps the Dutch text to `sepa_type`, `transaction_type`,
`direct_debit_type`, and `recurring`. Both parsers call it. A new payment type
then needs one edit.

### Select the Tikkie branch by `sepa_type`

The normalization of `transaction_type` breaks the present Tikkie branch of the
tagged parser. The branch compares against `SEPA OVERBOEKING`, which becomes
`SEPA Transfer`. The labelled parser already selects by `sepa_type`. The tagged
parser does the same, so one rule holds for both forms.

### Add a column, and do not change the transaction id

The reference becomes a new indexed column `end_to_end_reference` on the
transaction table. The duplicate check reads it as a second match key.

Alternative: derive the id from the reference, as for PayPal and Wise. Rejected.
That rewrites the id of each stored SEPA row. The next import would then write a
second row, and the manual categorization of the first row would lose its
transaction. The core beliefs do not allow that loss.

A new column needs an Alembic migration. The migration backfills the column from
`description_structured`, for the old key `reference` and for the new key
`end_to_end_reference`. The iOS companion needs the same GRDB migration.

### Use the account and the amount with the reference

A reference is unique for one creditor, and not for the world. The check
compares the account and the reference together.

The check also compares the amount. The sample statement of 2291 rows shows
why: it holds three pairs of a payment and its reversal, and each pair shares
one reference with the opposite sign. One pair is a direct debit of -149,88 with
its `SEPA INCASSO TERUGBOEKING` of +149,88. Those are two transactions. Without
the amount the check would join them, and the user would lose the reversal. The
two description forms of one payment always report the same amount, because
they describe one statement line, so the amount does not break the case that
this change targets.

The check normalizes the reference before each comparison: it removes each
whitespace character, each period, and each hyphen, and then changes the text to
upper case. Two reasons need this. The wrap of the description can fall inside
the reference, so one form reads `718085 5028127978` where the other reads
`7180855028127978`. The bank also prints one reference with different
separators, so one form reads `8022764496926345` where the other reads
`8022.7644 .9692.6345`. On a real database of 7202 rows the normalization
raises the count of the found duplicate pairs from 21 to 46. No added pair holds
two different dates, and none comes from one source file, so no added pair looks
like two payments. The rule matching already normalizes in the same manner,
through `normalize_string_for_matching`.

The column keeps the original text, so that the report and the page name what
the bank wrote.

The check ignores the empty value, the value `NONREF`, and the value
`NOTPROVIDED`. The same sample statement holds `NOTPROVIDED` 136 times. Without
that exclusion the check would fold 136 unrelated payments into one row. The
comparison removes each whitespace character first, because the description
wraps at a fixed width and the file also holds `NOTP ROVIDED`.

### Flag the row, and do not delete it

The merge writes `deleted_at` on each row that it removes from the lists. The
column exists, `live_only` is the one shared predicate of the seven readers, and
a snapshot already carries the value. Each total therefore corrects itself with
no change to a reader.

Alternative: delete the row. Rejected. A delete frees the id, and the next
import writes the row again. A delete also does not reach a second machine,
because a snapshot carries a row and not an absence.

### Add the column `merged_into`

`purge_flagged_transactions` and `_flagged_rows` both read `deleted_at` alone.
Each one would therefore treat a merged row as a row that the user flagged. The
purge would delete it, free its id, and let the next import write the duplicate
again. The new column separates the two kinds of flag.

The column also holds the audit trail of the merge and makes the undo possible.

Alternative: scope the purge to `is_manual == True`. Rejected. It stops the
purge, but it keeps no record of the row that absorbed the flagged row.

### Pick the survivor by the lowest id

The id is stable, and Python and Swift order a string in the same way. Two
machines therefore pick the same survivor with no sync.

Alternative: pick by the import order, by `source_line`, or by the richer
structured description. Rejected. Each one can differ between two machines. If
two machines pick two different survivors, a snapshot carries `deleted_at` for
both rows, and the payment disappears.

### Refuse a conflict of the manual categories

The core beliefs give the snapshot import the only right to replace a manual
categorization. The merge therefore refuses a group whose rows hold two
different manual categories, and it reports the group. The merge carries a
manual categorization only to a survivor that holds none.

## Risks / Trade-offs

- [The merge hides a payment that is not a duplicate] → The merge flags the row
  and keeps it. The user can read the report and undo the merge. Only the purge
  deletes a row, and the purge keeps each merged row.
- [The user purges before the undo] → The row goes away, and the undo reports
  that it cannot restore it. The purge keeps each merged row, so the user must
  flag the row by hand first.
- [A creditor reuses one reference for two payments of the same amount] → The
  system would count the second payment as a duplicate, and the user would lose
  it. The import report names each duplicate, so the user can see the loss. On
  the sample statement of 2291 rows the reference check adds no duplicate at
  all, so the risk is low. A regression test holds that number at zero.
- [The migration of the field target changes a categorization] → The migration
  runs through `record_rule_change`, so the report names each affected
  transaction. A manual categorization does not change.
- [The two apps fall out of step] → The Python change and the Swift change must
  land together. Each app runs the two one-time passes on its own, because each
  app imports a statement and applies the rules on its own. Either app may run
  first. Without the Swift passes a row that the iOS app wrote would keep the
  old keys, and it would churn on each sync: the desktop row and the iOS row
  would differ, so the snapshot merge would rewrite one of them every time.
- [The amount key differs between the two apps] → The key decides which rows
  form a group, so the two apps would merge different sets. A parity test holds
  the two implementations to the same string for seven amounts.

## Migration Plan

1. Add the column and the index with an Alembic migration.
2. Backfill the column from `description_structured`, for both key names.
3. Rename the keys in the parsers. The rules read the stored
   `description_structured`, and not the raw text, so a rename alone changes
   nothing for a stored row. Add a one-time pass that rewrites the stored
   structured description with the new parser. The pass SHALL select a row
   whose stored format is `sepa`, and also a row whose stored format is
   `mt940` with a `transaction_type` that starts with `SEPA`. A tagged SEPA row
   holds the format `mt940` today, so the second test selects exactly the rows
   that need `CSID` and `MARF` out of `other_fields`.
4. Derive the column on the snapshot-import path for a snapshot that holds no
   value for it. A snapshot from an app before this change holds no such key,
   because the snapshot format lists the columns of the transaction table.
5. Migrate the field target of each affected rule, and write the report.
6. Add the column `merged_into` in the same Alembic migration as the column
   `end_to_end_reference`. One migration keeps the two columns together.
7. Exclude a merged row from the purge and from the list of the flagged
   transactions, before the merge can write a row.
8. Offer the preview of the merge, the merge, the report, and the undo.
9. Port the same steps to `ios/DVMFinanceKit`.

Rollback: the column and the index drop without a loss, because the transaction
ids do not change. A rollback of the key rename needs the reverse pass of step 3
and step 4.
