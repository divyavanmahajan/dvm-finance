# Summary — 03 Parsers and Dedup

## Completed
2026-07-07

## Goal
All statement parsers (MT940/STA, ABN XLS, CSV, PayPal TXT, Wise CSV, SEB) and the
deterministic-id/dedup logic ported with tests passing.

## What Was Built
- `parsers/` package ported from abn-analyst `app/parsers/`: `description.py`,
  `mt940.py`, `xls.py`, `paypal.py`, `wise.py`, `seb.py`, `utils.py`, plus a new
  generic `csv.py` and the `parse_statement_file` dispatcher in `__init__.py`
  (dispatches .mt940/.mta/.sta/.txt -> MT940, .xls/.xlsx -> XLS, .csv -> generic CSV;
  PayPal/Wise/SEB dispatched explicitly by the importer).
- `config` dependency stripped: `DEFAULT_CURRENCY` now comes from `settings`.
- `core/utils.py`: ported `normalize_category`, `normalize_string_for_matching`,
  `calculate_transaction_hash_components` (shared with the rule engine).
- `core/dedup.py`: ported deterministic id recipe (account+date+amount+deschash;
  PayPal=account+paypal_id; Wise=account+wise_id; SEB=account+voucher), plus
  `check_duplicates` (DB + in-batch) and `insert_transactions` (merge-based, writes
  `transaction_hash`).
- Tests: ported `test_parser.py` -> `test_parsers.py` (MT940 + all description parsers),
  ported `test_paypal_parser.py` (fixture-based), new `test_wise_parser.py`,
  `test_seb_parser.py`, and `test_dedup.py` (id determinism, dup counting, PayPal/Wise/SEB
  id recipes). Fixtures under `tests/fixtures/`. 53 new tests (79 total).

## Key Decisions
- Ported the fuller `parse_mt940_description` Tikkie-IDEAL `payer_name`/EREF-timestamp
  extraction from legacy `parser.py` into `description.py` (the packaged legacy
  `parsers/description.py` was missing it — a pre-existing discrepancy the ported test
  exercised).
- SEB tests assert on network-independent fields (native SEK amount, voucher, structure)
  since the SEB parser fetches ECB rates online; EUR conversion is not asserted.
- Generic CSV parser reuses the XLS column mapping via `pandas.read_csv(sep=None)`.

## Deviations
- Added generic `csv.py` (task listed "the CSV path"; no legacy generic-CSV parser
  existed, so it was written fresh following the XLS parser's semantics).
- The SEB sample fixture contains legitimately duplicate voucher numbers, so the
  voucher-uniqueness assumption is not asserted (would collapse under the id recipe;
  matches legacy behavior).

## Files Changed
- src/abn_combined/parsers/{__init__,description,mt940,xls,csv,paypal,wise,seb,utils}.py
- src/abn_combined/core/{utils,dedup}.py
- tests/{test_parsers,test_paypal_parser,test_wise_parser,test_seb_parser,test_dedup}.py
- tests/fixtures/{paypal_sample.TXT,wise_sample.csv,seb_sample.csv,mt940_sample.STA}

## Verification
- `ruff check .` clean; `pytest` 79 passed.
