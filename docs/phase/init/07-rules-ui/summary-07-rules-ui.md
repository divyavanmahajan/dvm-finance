# Summary — 07 Rules UI: CRUD, Preview, Create-from-Transaction, History

## Completed
2026-07-07

## Goal
Full rules management on top of the step-04 engine: priority-ordered list, editor with
dynamic AND/OR condition rows, dry-run preview of an unsaved draft (with gains/losses/
changes diff for edits), one-click rule creation from a transaction, browsable change-
report history, and "Recategorize all" — with every mutation audited via
`record_rule_change` (Golden Principle 5).

## What Was Built
- `api/rules.py` (new router, claims `GET /rules` from the placeholder):
  - `GET /rules` — list ordered by `priority, id` with columns priority / type
    (+field target) / pattern / match value (+condition count) / category / tags /
    active switch / matched count linking to `/transactions?rule_id=N`, edit +
    per-rule-history + delete (hx-confirm) actions, "New rule", "History" and
    "Recategorize all" (confirm) buttons.
  - Editor: `GET /rules/new` (blank or `?from_transaction=<id>` prefilled),
    `GET /rules/{id}/edit`, `GET /rules/{id}` → 303 to edit (used by the
    transaction-detail "assigning rule" link from step 06).
  - `POST /rules/preview` — parses the *unsaved* draft form (works before the rule
    exists), builds a transient `DraftRule`/`DraftCondition` (never touches the
    session), runs `preview_rule` and renders `_rule_preview.html`: matched
    transactions and, when a hidden `rule_id` is present (edit), Gained / Lost /
    would-change sections. Regex errors from `RuleValidationError` render inline in
    the panel (HTTP 200), never a failure page.
  - Mutations — all flush then call `record_rule_change`: `POST /rules` (create),
    `POST /rules/{id}` (update, full condition replacement via delete-orphan),
    `POST /rules/{id}/toggle` (htmx row swap), `DELETE /rules/{id}` (row removal),
    `POST /rules/recategorize` → 303 to `/rules/history#report-N`. Validation
    (rule_type/pattern/operator whitelists, required fields, regex) re-renders the
    editor with inline errors at 400 and records nothing.
  - History: `GET /rules/history` (global, newest first) and `GET /rules/{id}/history`
    (matches `rule_id` OR the rule's `uuid`, and still works for deleted rules).
- `core/rule_prefill.py` (new): `prefill_rule_from_transaction` ports the legacy JS
  heuristics — structured `merchant_name` > `name` > `counterparty` →
  `structured_field` rule; structured `iban`/`payer_iban` → `account_iban` rule;
  else `keyword` on description. Seeds category (manual wins, first of a comma list),
  `filter_account` from the source account, and a "Created from transaction: …" note.
  `blank_rule_vm()` is the single source of the editor view-model shape.
- Templates: `rules.html` + `_rules_row.html` (toggle/delete swap partial),
  `rules_edit.html` (all fields, context-filter fieldset, Alpine condition rows,
  preview button with `hx-trigger="load, click"` when auto-previewing a
  from-transaction prefill), `_rule_preview.html` (counts pills + matched/gained/
  lost/changes tables), `rules_history.html` + `_rule_report.html`.
- `_rule_report.html` is deliberately generic: it renders a plain dict
  (`id/created_at/action/rule_id/rule_label/diff/summary/txn_changes`) built by
  `_report_vm`, so step-11 snapshot-import reports can render in the same list by
  producing the same shape (an `import` action badge style is already present).
- `web/static/js/rules.js`: Alpine `ruleEditor` — add/remove/move-up/move-down
  condition rows; sort order = row index via hidden `cond_sort_order`.
- `web/static/rules.css` (new stylesheet; `app.css` untouched).

## Key Decisions
- Preview uses transient dataclasses (`DraftRule`), not ORM instances, so a draft can
  never leak into the session or be flushed accidentally.
- Condition rows post as parallel arrays (`cond_field_target[]`…): no JS build step,
  works for both the Alpine UI and plain form posts in tests.
- `POST /rules/recategorize` and `/rules/preview` are registered before
  `POST /rules/{rule_id}` (Starlette matches in order; "recategorize" would otherwise
  422 as a non-int rule_id).
- Report view-model names the per-transaction list `txn_changes`, not `items` —
  Jinja resolves `dict.items` to the method, shadowing a key named `items`.
- History transaction links use `/transactions?q=<description>` (there is no
  by-id page filter); the raw transaction id is always shown alongside.
- Delete keeps the audit trail: the report stores `rule_id`/`rule_uuid` from the
  pre-delete snapshot, and per-rule history remains reachable after deletion.

## Deviations
- None from the step-04 engine — `apply_rules`/`preview_rule`/`record_rule_change`
  covered everything; no adapter needed.
- Legacy `static/js/transactions/` directory is empty in abn-analyst; the prefill
  heuristics were ported from `static/js/transactions.js`
  (`createRuleFromTransaction`) instead, extended with the iban/payer_iban →
  `account_iban` branch the task called for.
- Legacy JSON endpoints (export/import/reorder, per-condition CRUD) were not ported:
  conditions are edited inline and replaced wholesale on save; rule import/export
  arrives with snapshots (step 11 / FR9).

## Files Changed
- src/abn_combined/api/rules.py (new)
- src/abn_combined/core/rule_prefill.py (new)
- src/abn_combined/web/templates/{rules,rules_edit,rules_history}.html (new)
- src/abn_combined/web/templates/{_rules_row,_rule_preview,_rule_report}.html (new)
- src/abn_combined/web/static/rules.css (new)
- src/abn_combined/web/static/js/rules.js (new)
- tests/test_rules_ui.py (new, 33 tests), tests/test_rule_prefill.py (new, 10 tests)
- docs/phase/init/07-rules-ui/screenshots/{rules-list,editor-conditions,preview-diff,create-from-transaction,history-report}.png

## Verification
- `ruff check` clean on all step-07 files; full `pytest -q` green (all pre-existing
  tests included, none excluded).
- 43 tests added: prefill heuristics units; TestClient coverage of list ordering,
  matched-count links, create/update/toggle/delete each producing a
  `RuleChangeReport` with correct before/after snapshots, condition round-trips
  (AND/OR + sort order), validation (regex/type/required → 400, no rule, no report),
  preview for drafts and edits (gains/losses, no writes, inline regex error,
  AND-condition filtering), from-transaction prefill (structured/iban/auto-preview/
  404), history rendering (order, txn diffs, per-rule scoping), recategorize-all
  (report + manual precedence preserved — Golden Principle 2).
- Headless Playwright against a seeded temp data dir: full flow exercised — list,
  editor with added/reordered OR condition, edit preview showing Lost/changes diff,
  `/rules/new?from_transaction=…` auto-running its preview then saved and visible in
  the list, history showing the create diff and the recategorize report with
  expanded changed-transaction lists. Screenshots captured (5).
