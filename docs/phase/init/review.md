# Phase Review: init

## Review Date
2026-07-08

## Reviewer
spec-review

## Branch
phase/init

## Overall Verdict
APPROVED WITH WARNINGS

---

## Findings

### Spec Compliance
**Result**: Pass
All ten functional requirement groups (FR1–FR10) are implemented and traceable to step summaries: uvx packaging with data-dir handling (01, 13), transactions view with URL-state filtering and manual-precedence edits (06), trends table with provably exact click-through (08), full rule engine with preview + persisted change reports for every mutation (04, 07), tags/budgets/cash flow (09), UI-triggered ABN/PayPal downloads as background jobs (10), manual upload for all six formats (05, 03), snapshot export/import with incoming-wins, backup, and audit report (11), legacy migration verified against the real database — 6,019 transactions, 701 rules, idempotent, source untouched (12). NFRs: localhost-only default, SQL aggregation, 50k reapplication ~3.9s (<10s), no-JS-build vendored frontend, app works without Playwright browsers, coverage 88.84% ≥ 80 gate, structured logging. Non-goals respected: no LLM, MCP, auth, charts, or Docker anywhere. Deviations recorded per step are all justified and none violate the spec. One spec item is not yet fully verified: FR7's real bank flows (see Warnings).

### Step Completeness
**Result**: Pass
13/13 steps `done` in status.md; every step folder has a `summary-*.md` (no leftover `progress-*.md`); step folders include screenshots as browser evidence. Files listed in summaries exist on disk (spot-checked).

### Schema and Boundary Validation
**Result**: Warning
Validation happens at entry everywhere, but through FastAPI's per-endpoint mechanisms rather than a single shared schema layer: the upload API uses Pydantic response/request models; the ~18 form endpoints (rules, budgets, tags, snapshots) rely on FastAPI `Form()`/`Query()` type validation plus explicit domain validation (regex patterns, snapshot schema_version/integrity, filter parsing in `core/filters.py` — which *is* a shared, tested boundary contract for the URL state). Validation failures are structured (400/422 with messages, no silent coercion). Acceptable for a server-rendered single-user app, but there is no `schemas/` module and Pydantic usage is uneven.

### Shared Code and Duplication
**Result**: Pass
Shared logic is centralized in `core/` (filters, rule engine, importer, renames, snapshots, jobs, utils) and reused across API modules; parsers ported into one package with a single dispatcher. The router auto-registration pattern kept parallel steps from duplicating wiring. No notable duplication found.

### Code Quality
**Result**: Pass
`ruff check .` clean. No hardcoded secrets/credentials (grep verified). No dead code or debug leftovers observed in spot checks. Known legacy quirk (OR-condition folding) deliberately preserved and documented in tests per the port-don't-rewrite principle. Downloads run in worker threads to keep the Playwright sync API off the event loop.

### Tests
**Result**: Pass
447 unit/integration tests, 5-flow e2e suite + snapshot e2e (6 e2e total), 1 slow perf test. Re-verified independently on the phase branch during this review: `pytest` exit 0, `pytest -m e2e` exit 0, `pytest --cov=abn_combined` exit 0 with `fail_under=80` enforced (88.84%). Edge/error paths covered at boundaries (corrupt snapshots, invalid regex, unknown legacy schema, auth timeout, CDP unreachable, transactional rollback tests).

### Demo Document
**Result**: Warning
`demo.md` was not produced: `showboat` (and `rodney`) are not installed on this machine. This is documented with justification in `phase-summary.md`. Visual evidence exists as per-step Playwright screenshots (21+ images across step folders) plus e2e tests that re-verify the same flows executably.

### Documentation
**Result**: Pass
`phase-summary.md` complete; `docs/architecture.md` (incl. snapshot format + hyphen separator), `docs/developer.md` (e2e harness, packaging note), `docs/product.md`, and `README.md` all updated by step 13 to match reality. `CLAUDE.md` created with the phase-summary reference link (34 lines — well under the size threshold). New commands/flags are documented.

### Git Hygiene
**Result**: Pass
Working tree clean; 26 commits on `phase/init`, all step-referenced (`[init/NN-…]`); `main` contains only the initial docs commit, so no conflicts (`git diff main...HEAD`: 190 files, +33,915). No remote configured — nothing to fetch; merge will be local.

---

## Required Changes
None.

## Warnings
1. **Real download flows unverified** (Spec Compliance / FR7): ABN AMRO and PayPal downloads are covered by ported mocked protocol tests only. A manual session with live credentials is needed to confirm the end-to-end flows against today's bank endpoints.
2. **No centralized schema layer** (Boundary Validation): validation is FastAPI-idiomatic per endpoint rather than a shared `schemas/` module; Pydantic models exist only on the upload API.
3. **demo.md skipped** (Demo Document): showboat unavailable; screenshots + e2e suite stand in as evidence.

## Recommended Next Steps
Approve the merge of `phase/init` into `main` (warnings 2–3 are reasonable accepts for a local single-user app; log accepted warnings to the tech-debt tracker), then schedule the manual live-download verification session for warning 1.
