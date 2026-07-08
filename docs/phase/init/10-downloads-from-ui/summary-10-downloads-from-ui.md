# Summary: 10 — Downloads from the Web UI

## Completed
2026-07-07

## Goal
The Download tab triggers the ABN AMRO (Playwright) and PayPal (CDP) download flows as
background jobs with live htmx-polled status, then imports files through the step-05
pipeline (FR7, NFR5).

## What Was Built
- `core/jobs.py`: thread-safe in-process `JobRegistry` (module singleton via
  `get_registry()`), one `DownloadJob` per source, `JobState` StrEnum
  (pending → waiting-for-auth → downloading → importing → done/failed), terminal
  states set `finished_at`; `is_running()` gates one-job-per-source.
- `downloaders/abn.py`: ported from abn-download/abn_download.py, protocol code kept
  diff-able — headed Chromium, cookie-banner dismissal, `wait_for_url` auth wait
  (5-min timeout → failed + browser closed), `page.request.post` to
  `mutationreporting/generations/v1` with the exact generations payload, base64 MT940
  decode into the statements dir, each file fed to `import_file`; updates
  `download_state` bookmark on success. `run_abn_job` is the worker-thread entry.
- `downloaders/paypal.py`: ported from paypal_download.py — CDP connect to
  `localhost:9222` (connect failure → immediate FAILED with the exact macOS Chrome
  launch command), CSRF response-listener + explicit `/reports/dlog` fetch fallback
  (module-global `_csrf_token` replaced by a per-job `csrf_state` dict), `reportCreate` →
  `reports` polling (interactive countdown replaced by job-status messages with poll
  counter) → `download` (JSON-base64 or raw bytes); `.TXT` saved and imported with
  `fmt="paypal"`; browser.disconnect keeps the user's Chrome open.
- `api/downloads.py`: `GET /download` page (replaces placeholder), `POST
  /api/download/{abn,paypal}` start endpoints (409 while running, 503 for ABN without
  Playwright), `GET /api/download/{source}/status` htmx partial. Date defaults read
  `download_state` ("since last successful download" + 1 day; DD-MM-YYYY for ABN,
  YYYY-MM-DD for PayPal), editable in the form. `_playwright_available()` checks
  chromium executable presence (NFR5).
- Templates `download.html` (per-source cards, disabled button while running, chrome
  launch command, install-instructions block replacing the ABN form when Playwright
  browsers are missing) and `_download_status.html` (state badge, message, poll via
  `hx-trigger="every 2s"` that stops on done/failed, final summary with
  `/transactions?source_file=...` links). New `web/static/downloads.css` imported from
  the page content block (base.html has no head block and is owned by step 01).
- `pyproject.toml`: added `downloads = ["playwright"]` optional extra (single allowed edit).

## Key Decisions
- Playwright sync API runs in daemon worker threads started by the route handlers —
  never on the event loop; the worker opens its own DB session via
  `get_session_factory()` (engine created with `check_same_thread=False`).
- CSRF state is a per-job dict threaded through the PayPal helpers instead of the
  source's module-level global, so concurrent/successive jobs can't leak tokens.
- `JobState` is a `StrEnum` so Jinja renders the raw value ("failed"), not
  "JobState.FAILED".
- Route handlers import the worker functions at request time so tests can monkeypatch
  `run_abn_job`/`run_paypal_job` without launching browsers.
- ABN default accounts kept from the source script (`_DEFAULT_ACCOUNTS`).

## Deviations
- Real ABN AMRO and PayPal end-to-end flows are NOT verified — they require live bank
  credentials/app auth and a user-launched CDP Chrome. **Pending: manual verification
  session with the user** (already listed as a blocker in status.md).
- downloads.css is loaded via `<style>@import ...</style>` inside the content block
  because base.html exposes no head block and is off-limits this wave.
- Per-account `download_state` granularity: bookmark is stored per source with
  `account=NULL` (the ABN generations call covers all accounts in one request); the
  schema supports per-account rows for later refinement.
- Screenshots taken of the page in three states (Playwright available / missing /
  running+done jobs) instead of a live bank run.

## Files Changed
- src/abn_combined/core/jobs.py (new)
- src/abn_combined/downloaders/{__init__,abn,paypal}.py (new)
- src/abn_combined/api/downloads.py (new)
- src/abn_combined/web/templates/{download,_download_status}.html (new)
- src/abn_combined/web/static/downloads.css (new)
- pyproject.toml (added `downloads` optional extra)
- tests/{test_jobs,test_downloads,test_downloads_routes}.py (new — 83 tests)
- docs/phase/init/10-downloads-from-ui/screenshots/download-page-{playwright-available,playwright-missing,job-states}.png

## Verification
- `ruff check` clean on all step-10 files (repo-wide failures belong to parallel steps).
- 83 new tests green; full suite was 263 passed at last stable-tree run (later repo-wide
  failures are from other agents' in-flight files, none touch step-10 code).
- Download page rendered headless in three states; screenshots saved.
