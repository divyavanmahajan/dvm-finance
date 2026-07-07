# 10 — Downloads from the Web UI

## Goal
The Download tab triggers the ABN AMRO (Playwright) and PayPal (CDP) download flows as background jobs with live status, then imports files through the step-05 pipeline.

## Context
Spec FR7 — the abn-download functionality, moved from CLI prompts to server-side background jobs with htmx status polling.

## Prerequisites
05-import-pipeline-and-upload.

## Tasks
1. Job infrastructure: an in-process job registry (one job per source at a time) run in worker threads (Playwright sync API must not run on the event loop); states pending → waiting-for-auth → downloading → importing → done/failed(message); status endpoint polled via htmx every 2 s.
2. Port `abn_download.py`: headed Chromium via Playwright, navigate to ABN transactions URL, wait for authenticated state (timeout → failed state, browser closed), `page.request.post` to `mutationreporting/generations/v1`, decode base64 MT940s into the data dir, feed each file to the import pipeline. Replace CLI prompts/args with job parameters.
3. Date-range defaulting: read/write `download_state` per source/account — default "since last successful download", editable in the form (DD-MM-YYYY semantics preserved internally).
4. Port `paypal_download.py`: CDP connect to `localhost:9222` (UI shows the exact Chrome launch command when connection fails), CSRF response-listener, `reportCreate` → poll `reports` (poll progress surfaced in job status, replacing the interactive countdown) → `download`; save `.TXT`, import.
5. Download page: per-source card with date-range form, start button (disabled while a job runs), live status area, and the final import summary linking to `/transactions?source_file=...`. If Playwright browsers are missing, show `playwright install chromium` instructions instead of the ABN form (NFR5).
6. TDD: port abn-download's mocked tests (payload structure, MT940 decode, CSRF extraction, QL payloads, polling) against the refactored modules; job-state-machine unit tests (auth timeout, CDP unavailable, import failure); route tests for status polling. Manual browser verification of the real ABN and PayPal flows end-to-end (real bank auth — cannot be automated); screenshots of job progression.

## Acceptance Criteria
- Mocked download tests green; job state machine covers all failure paths without hangs.
- Real ABN AMRO download verified manually: authenticate → files land → transactions imported and categorized.
- Real PayPal download verified manually via CDP Chrome.
- App still fully usable when Playwright browsers are absent (message shown).
- `pytest` green, `ruff check .` clean.

## Notes
- > ⚠ Golden Principle 1: port downloader internals — the HTTP/protocol logic must not be reinvented.
- Only the job wrapper is new; keep protocol code diff-able against abn-download for future bank changes.

## External References
- `docs/references/abn-amro-protocol-reference.txt`, `docs/references/paypal-protocol-reference.txt`, `docs/references/playwright-reference.txt`.
- Sources: `/Users/divya/projects/abn-download/abn_download.py`, `paypal_download.py`, `cdp_capture.py`, `tests/`.
