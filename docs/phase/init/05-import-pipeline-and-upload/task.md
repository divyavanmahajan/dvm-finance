# 05 — Import Pipeline and Manual Upload

## Goal
A single import pipeline (parse → dedup → insert → apply rules → summary) exposed via an upload API and an Upload page for all supported formats.

## Context
Spec FR8. Downloads (step 10) reuse this pipeline; this step makes the app usable end-to-end for the first time.

## Prerequisites
04-rule-engine.

## Tasks
1. `core/importer.py`: `import_file(db, path_or_bytes, filename)` → dispatch to parser, dedup, insert, `apply_rules` on new transactions, return summary (new, duplicates skipped, categorized, uncategorized). Store the uploaded file in the data dir under `statements/`.
2. API: `POST /api/upload` (multipart, format auto-detected by extension/content as in abn-analyst; explicit format override param for PayPal/Wise/SEB where the legacy app had separate endpoints).
3. Upload page: drag/drop or file picker (plain form + htmx), format hint, and the import summary rendered after completion with a link to the new transactions (filtered by source file).
4. Error handling: unparseable file → 422 with a human message shown inline; never a stack trace to the UI.
5. TDD: TestClient tests per format fixture (counts correct, rules applied), duplicate re-upload test, bad-file test. Browser verification with a real fixture file + screenshot.

## Acceptance Criteria
- Uploading each fixture format via the UI shows a correct summary and the transactions appear in the DB with rule categories.
- Re-upload shows all-duplicates summary.
- `pytest` green, `ruff check .` clean, browser screenshot captured.

## Notes
- Transactions page doesn't exist yet (step 06); link target can 404 until then — keep the URL scheme (`/transactions?source_file=...`) consistent with step 06's filter design.

## External References
- Source: `/Users/divya/projects/abn-analyst/app/routes/upload.py`.
