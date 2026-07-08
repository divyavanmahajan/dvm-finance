# Summary — 05 Import Pipeline and Manual Upload

## Completed
2026-07-07

## Goal
A single import pipeline (parse -> dedup -> insert -> apply rules -> summary) exposed via
an upload API and an Upload page for all supported formats.

## What Was Built
- `core/importer.py`: `import_file(db, content, filename, statements_dir, fmt="auto")`
  stores the file under `statements/` (uuid-prefixed name; user-facing `source_file` kept as
  the original name), parses (explicit fmt for paypal/wise/seb/csv, else extension-based
  `parse_statement_file`), dedups, inserts, applies rules to the new rows, and returns an
  `ImportSummary` (new / duplicates / categorized / uncategorized / new_ids). Unparseable or
  empty files raise `ImportError_`.
- `api/upload.py`: `GET /upload` page and `POST /api/upload` (multipart). `UploadParams`
  Pydantic model validates the `format` field (Literal auto/paypal/wise/seb/csv). Returns an
  htmx inline-summary partial for HX requests, JSON otherwise. Bad/empty file -> 422 with a
  human message (no stack trace).
- `create_app` reordered to register routers first, then add placeholders only for nav paths
  not already claimed (so `/upload` is the real page).
- Templates: `upload.html` (file picker + format select + htmx post + indicator),
  `_upload_summary.html` (counts + "View the new transactions" link to
  `/transactions?source_file=...`).
- Tests: `test_upload.py` — per-format `import_file` (PayPal/Wise/SEB/MT940), reimport =
  all duplicates, rules applied, bad/unknown-format raises; API JSON summary, htmx partial,
  duplicate re-upload, bad-file 422, invalid-format 422. Upload page render. 15 tests
  (125 total incl. slow).

## Key Decisions
- Stored filename is uuid-prefixed for collision safety; `source_file` is overridden to the
  original name after parsing so the transactions deep-link stays clean.
- Reimport duplicate count includes both DB-existing and in-batch repeats (the real MT940
  fixture has 19 in-batch duplicate ids), so counts are total-parsed on re-upload.
- htmx-aware endpoint returns a partial or JSON based on the `HX-Request` header.

## Deviations
- Transactions page does not exist yet (step 06); the summary's "View the new transactions"
  link uses the agreed `/transactions?source_file=...` scheme and will 404 until step 06.

## Files Changed
- src/abn_combined/core/importer.py, src/abn_combined/api/{__init__,upload}.py
- src/abn_combined/app.py (router-first placeholder logic)
- src/abn_combined/web/templates/{upload,_upload_summary}.html
- tests/{conftest.py (eager migrations),test_upload.py}
- docs/phase/init/05-import-pipeline-and-upload/screenshots/{upload-form,upload-summary}.png

## Verification
- `ruff check .` clean; `pytest` 124 (+1 slow) passed. Browser: imported a PayPal fixture via
  the UI, 89 new transactions, inline summary + deep-link rendered (screenshot captured).
