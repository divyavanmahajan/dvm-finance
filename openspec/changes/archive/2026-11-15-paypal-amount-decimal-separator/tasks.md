# Tasks

Use made-up amounts and ids in each test and fixture. Do not copy a value from a real statement.

## 1. PayPal number parser (Python)

- [x] 1.1 Add failing cases to `test_parse_european_number` in `tests/test_paypal_parser.py`: `-12,34`, `-12.34`, `1.458,32`, `1,458.32`, `1.458`, `1,5`, `abc`, and an empty value. Verify that the period cases fail.
- [x] 1.2 Change `_parse_european_number` in `parsers/paypal.py` so the last separator decides (design decision 1). Verify that the tests of 1.1 pass and that `test_parse_paypal_file` still passes on the comma fixture.
- [x] 1.3 Add a small made-up report with period decimals under `tests/fixtures/`, and a test that parses it to the expected amounts. Verify that the test passes.

## 2. PayPal number parser (Swift)

- [x] 2.1 Add the cases of 1.1 to `ParserTests.swift`, and change `PayPalParser.parseEuropeanNumber` with the same rule. Name the Python origin in the doc comment. Verify with `xcodegen generate && xcodebuild test`, and verify that `testPayPalFixtureParity` still passes.

## 3. Amount correction on import

- [x] 3.1 Write failing tests in `tests/test_upload.py`: a re-import with a changed amount corrects the row, keeps the manual category and the manual tags, sets `updated_at` and a new `transaction_hash`, and counts one corrected and zero duplicates. Verify that the tests fail.
- [x] 3.2 Add tests for the rows that the import must not change: an equal amount, a flagged row, and a duplicate that matched through the end-to-end reference. Verify that they fail or pass for the right reason.
- [x] 3.3 Add `correct_amounts(db, duplicates)` to `core/importer.py`, and the fields `corrected` and `corrections` to `ImportSummary`. Call the function from `import_file` and log each correction. Verify that the tests of 3.1 and 3.2 pass.
- [x] 3.4 Show the corrected count and the table of corrections in `_upload_summary.html`, and add `corrected` to the `upload_imported` log line. Verify with client tests for the fragment and for the JSON response.

## 4. Docs

- [x] 4.1 Describe the amount correction on import in `docs/product.md`, in ASD-STE100. State that the user exports a snapshot for the phone after a correction. Verify that the text matches the summary in the UI.

## 5. Integration checks

- [x] 5.1 Run `pytest`, `pytest --cov=abn_combined`, and `ruff check .`. Verify that all pass and that the coverage stays at 80% or more.
- [x] 5.2 Run `openspec validate paypal-amount-decimal-separator --strict`. Verify that it passes.

## Workflow follow-up

- After the change ships, the user imports the affected PayPal report again into the real data. The summary must show two corrected transactions. The user then exports a snapshot for the phone.
- Archive the change after the user accepts it.
