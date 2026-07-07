# 03 — Parsers and Dedup

## Goal
All statement parsers (MT940/STA, ABN XLS, CSV, PayPal TXT, Wise CSV, SEB) and the deterministic-id/dedup logic are ported with their tests passing.

## Context
The import pipeline (step 05) and downloads (step 10) feed everything through these parsers. Spec FR8.1–8.2.

## Prerequisites
02-database-schema.

## Tasks
1. Port from `abn-analyst/app/parsers/` into `abn_combined/parsers/`: `mt940.py`, `xls.py`, `paypal.py`, `wise.py`, `seb.py`, `description.py`, `utils.py`, plus the CSV path and the dispatcher from `app/parser.py`. Strip any LLM/auth imports encountered.
2. Port shared helpers from `abn-analyst/app/utils.py`: `normalize_category`, `normalize_string_for_matching`, `calculate_transaction_hash_components` — into `core/` (they are also used by the rule engine).
3. Port deterministic id generation and duplicate handling: id = `account + date + amount + description_hash`; PayPal id = `account + paypal_transaction_id`; `transaction_hash` computation; insert path that skips exact duplicates and counts them (`insert_transactions`, `check_duplicates` equivalents).
4. Copy fixture statement files and the existing parser tests from both repos (`test_parser.py`, `test_paypal_parser.py`, Wise/SEB tests if present); adapt imports; add missing fixture-based tests for any parser lacking one (TDD for gaps).
5. Unit tests for id determinism (same input → same id; changed amount → new id) and dedup counting.

## Acceptance Criteria
- Every supported format parses its fixture file into `Transaction` rows with correct fields.
- Re-importing the same fixture reports N duplicates, inserts 0.
- `pytest` green, `ruff check .` clean.

## Notes
- > ⚠ Golden Principle 1: port, don't rewrite — copy the parser code and tests, adapt imports only.
- > ⚠ Golden Principle 10: deterministic identity — do not change the id recipe; snapshots and legacy migration depend on it.

## External References
- Sources: `/Users/divya/projects/abn-analyst/app/parsers/`, `/Users/divya/projects/abn-analyst/app/parser.py`, `/Users/divya/projects/abn-analyst/app/utils.py`, tests in `/Users/divya/projects/abn-analyst/tests/`.
