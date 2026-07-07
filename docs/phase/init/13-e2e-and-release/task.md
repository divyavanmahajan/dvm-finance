# 13 — E2E Suite, Coverage Gate, and Release Polish

## Goal
The five main user flows pass as Playwright e2e tests, coverage ≥ 80%, docs are current, and the app runs cleanly via uvx.

## Context
Spec Testing section + Success Metrics. Final hardening before closing the phase.

## Prerequisites
All previous steps.

## Tasks
1. E2E harness: pytest fixture that starts the app on a random port against a seeded temp data dir; pytest-playwright drives Chromium (headless in CI mode, headed for manual runs).
2. E2E cases (spec User Flows): (a) upload fixture → transactions appear categorized; (b) filter Uncategorized → create rule from transaction → preview → save → change report visible in History; (c) Trends cell click-through → filtered list sums to cell value; (d) edit rule → preview diff → save → history; (e) snapshot export from seeded dir A → import into empty dir B → data present, report shown. Download flows covered by mocked tests only (step 10); real flows re-verified manually.
3. Coverage: run `pytest --cov=abn_combined`; raise gaps to ≥ 80%; wire the threshold into config so it fails the suite.
4. Accessibility/polish pass: keyboard focus order in filter bar and rule editor, form labels, `hx-indicator` loading states, empty-state pages for a fresh install.
5. README: install (`uvx abn-combined`), first run, migration, sharing workflow, PayPal Chrome command, snapshot security note (unencrypted financial data).
6. Update `docs/architecture.md`, `docs/developer.md`, `docs/product.md` to match reality; resolve spec Open Questions (record PyPI name decision).
7. Final manual browser walkthrough of all tabs with real (migrated) data; screenshots archived.

## Acceptance Criteria
- `pytest` (unit + integration + e2e) fully green with coverage ≥ 80%; `ruff check .` clean.
- `uvx --from <repo> abn-combined` on a clean machine/dir reaches a working empty app.
- README enables the second user to go from nothing to imported snapshot without help.

## Notes
- > ⚠ Golden Principle 7: this step is the backstop, not the first time tests are written — every prior step ships its own tests.
