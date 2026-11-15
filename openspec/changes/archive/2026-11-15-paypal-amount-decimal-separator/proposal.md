# Proposal

## Why

The PayPal parser always reads a period as the thousands separator and a comma
as the decimal separator. A new PayPal Activity Report writes its amounts with a
period as the decimal separator. The parser therefore stores an amount of 9.99
as 999, which is 100 times too large.

An import of the same report again does not repair the stored rows. The
PayPal transaction id does not hold the amount, so the import sees each row as a
duplicate and skips it.

## What Changes

- The PayPal parser finds the decimal separator from each amount. It reads
  `-9,99`, `-9.99`, `1.458,32`, and `1,458.32` correctly.
- The iOS PayPal parser gets the same change, so the two apps stay equal.
- An import corrects the amount of a stored transaction when the incoming row
  has the same id but a different amount. The upload summary shows the count
  of corrected rows and the old and new amount of each row.
- The automatic import after a download uses the same import path, so it also
  corrects amounts.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `statement-parsers`: The requirement "European amount format" changes. The
  PayPal parser reads both decimal separators.
- `statement-upload`: A new requirement lets an import correct the amount of a
  stored transaction with the same id.

## Impact

- `src/abn_combined/parsers/paypal.py`: the number parser.
- `src/abn_combined/core/dedup.py` and `core/importer.py`: the duplicate check
  returns the amount corrections, and the import writes them.
- `src/abn_combined/web/templates/_upload_summary.html`: the corrected rows.
- `ios/DVMFinanceKit/Sources/DVMFinanceKit/Parsers/PayPalParser.swift`: the
  same number parser.
- Tests: `tests/test_paypal_parser.py`, `tests/test_dedup.py`,
  `tests/test_upload.py`, and the Swift `ParserTests.swift`.
- Data: after the change, the user imports the affected report again. This
  corrects the two stored rows.
- No schema change and no snapshot format change.
