# 07 — Rules UI: CRUD, Preview, Create-from-Transaction, History

## Goal
Full rules management: priority-ordered list, editor with dynamic conditions, live preview of matches/changes before save, one-click rule creation from a transaction, and browsable change-report history.

## Context
Spec FR4.3–4.7 on top of the step-04 engine. This is the workflow the user values most.

## Prerequisites
06-transactions-view.

## Tasks
1. Rules list page: ordered by priority, columns (priority, type, pattern, value, category, tags, active toggle, matched-transaction count linking to `/transactions?rule_id=N`), delete with confirm. Active toggle and delete go through `record_rule_change`.
2. Rule editor (`/rules/new`, `/rules/{id}/edit`): all fields, context filters, dynamic condition rows (add/remove, AND/OR, sort order) via htmx/Alpine; regex validated server-side on preview/save.
3. **Preview panel**: "Preview matches" posts the draft (unsaved) form to a preview endpoint using `preview_rule`; renders matched transactions and, for edits, the gains/losses/changes diff. Must work before the rule exists.
4. **Create from transaction**: `/rules/new?from_transaction=<id>` prefills type/field/match value (description or counterparty/IBAN heuristics ported from legacy JS `transactions/` module), account filter, and auto-runs the preview.
5. **History**: `/rules/history` (global, newest first) and per-rule history; each report shows action, timestamp, before/after rule snapshot diff, summary counts, and expandable list of changed transactions (old → new category/tags) with links. Include recategorize-all and snapshot-import reports.
6. "Recategorize all" button (with confirm) surfacing the resulting report.
7. TDD: TestClient tests for CRUD + conditions endpoints (port/adapt legacy route tests), preview endpoint (draft + edit diff), create-from-transaction prefill, history rendering. Browser verification of the full flow: create rule from a transaction → preview → save → history shows the report; screenshots.

## Acceptance Criteria
- Every rule mutation is visible in History with correct per-transaction diffs.
- Preview on an edited rule correctly shows transactions gained, lost, and changed.
- Create-from-transaction produces a sensible prefilled rule in ≤ 2 clicks from the Transactions view.
- `pytest` green, `ruff check .` clean, screenshots captured.

## Notes
- > ⚠ Golden Principle 5: every rule change auditable — no mutation path may bypass `record_rule_change`.
- Legacy references for prefill heuristics: `abn-analyst/static/js/transactions/`, `categorization-rules.js`.

## External References
- Source: `/Users/divya/projects/abn-analyst/app/routes/categorization_rules.py`.
