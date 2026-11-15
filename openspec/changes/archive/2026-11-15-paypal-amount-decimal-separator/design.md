# Design

## Context

`_parse_european_number` in `parsers/paypal.py` removes each period and then
reads the comma as the decimal separator. The Swift port
`PayPalParser.parseEuropeanNumber` does the same. Each earlier PayPal report
uses a comma, so the bug shows only with a report that uses a period.

`generate_transaction_id` builds a PayPal id from the account and the PayPal
transaction id. The id does not hold the amount. `check_duplicates` therefore
puts a wrong stored row and its corrected incoming row in the duplicate list.
`import_file` then skips the incoming row.

`core/dedup.py` also holds uncommitted work for the merge of duplicates. This
change must not depend on that work, and it must not change the signature of
`check_duplicates`.

## Goals / Non-Goals

**Goals:**
- Parse both decimal separators in the PayPal parser, on desktop and on iOS.
- Let an import of a report correct the stored amount, with a visible record.

**Non-Goals:**
- No change to the other parsers. The MT940, the bank CSV, the Wise, and the
  SEB parsers do not use this function.
- No correction of other fields, such as the date or the description.
- No amount correction in the iOS import. The phone gets the corrected amount
  through a snapshot from the desktop. The iOS parser change stops new wrong
  rows on the phone.
- No stored import report on the desktop. The desktop has no such table today.
  The summary and the log hold the record.

## Decisions

### 1. The last separator decides

The parser looks at the last period or comma in the amount. If one or two
digits follow it, it is the decimal separator. The parser removes each other
period and comma. Otherwise the parser removes each period and comma, and the
amount is a whole number.

Alternative: detect the format once for each file, from the header or from the
first amount. A file with only whole amounts gives no answer, and a header
does not name the number format. We reject it.

Alternative: use the locale of the report. The report does not state its
locale. We reject it.

The PayPal amounts always have two decimals, so a separator with three digits
after it is always a thousands separator.

### 2. A separate correction step in the importer

A new function `correct_amounts(db, duplicates)` in `core/importer.py` runs
after `check_duplicates`. For each duplicate, it computes the id with
`generate_transaction_id`. It loads the stored row with that id. It skips a
missing row, a flagged row (`deleted_at` is set), and a row with the same
amount at two decimals. For each other row, it writes the new amount and a new
`transaction_hash`, because the hash holds the amount. It returns one record
for each correction: the id, the old amount, and the new amount.

A duplicate that matched through the end-to-end reference or the counterparty
has a different id, so the function finds no stored row with that id and skips
it. This gives the scenario "The duplicate comes from the end-to-end
reference" with no extra code.

The function handles each id once, so an in-batch duplicate does not correct a
row twice.

Alternative: change `check_duplicates` to return a third list. This changes a
function that the uncommitted merge work also changes. We reject it.

### 3. The summary carries the corrections

`ImportSummary` gets `corrected: int` and `corrections: list[dict]`. The
`duplicates` count excludes the corrected rows. The upload fragment shows the
count and a short table of the corrections. The JSON response holds the same
data. The importer logs each correction with the id and the two amounts.

The automatic import after a download calls `import_file`, so it gets the
correction with no extra change.

### 4. No rule run after a correction

No rule matches on the amount, so a correction does not change a category. The
importer does not run the rules again for a corrected row.

## Risks / Trade-offs

- [A snapshot from the phone or from a partner holds the old amount. The
  incoming values win, so a snapshot import puts the wrong amount back.] →
  Export a snapshot from the desktop after the correction, and import it on the
  phone first. The tasks state this order.
- [A file with a wrong amount for an id would overwrite a correct stored
  amount.] → The provider writes one amount for each transaction id. The
  summary lists each correction, so the user sees each change.
- [`updated_at` must change, or a delta snapshot does not hold the correction.]
  → The column has no automatic update. `correct_amounts` sets
  `updated_at = datetime.now()`, as `categorizer.py` and `manual_txn.py` do. A
  test checks it.

## Migration Plan

No schema change. After the deploy, the user imports the affected PayPal report
again. The summary must show two corrected transactions. Then the user exports
a snapshot for the phone.
