# Summary — 04 Rule Engine, Preview, Change Reports

## Completed
2026-07-07

## Goal
Categorization engine applying rules by priority with full condition/filter semantics,
a dry-run preview for a draft rule, and a persisted RuleChangeReport for every mutation.

## What Was Built
- `core/categorizer.py`, ported from abn-analyst `analyzer.py` (rule part only — no LLM):
  - Matching: `_apply_match_pattern` (contains/exact/starts_with/ends_with/regex),
    `_check_primary_condition` (keyword/account_iban/structured_field/full_description,
    IBAN extraction), `_evaluate_single_condition` (AND/OR), context filters
    (account/currency/date), all via `normalize_string_for_matching`.
  - `apply_rules(db, transaction_ids=None)`: sets `category`/`tags`/`categorization_source`
    = str(rule.id); no match -> category None; **skips** transactions with
    `categorization_source == "manual"`; never touches manual_category/manual_tags;
    returns `TxnChange` diffs.
  - `preview_rule(db, draft, existing_rule_id)`: dry-run returning matched, gains,
    losses (old-version matches the draft no longer matches), and per-transaction
    category/tag changes simulated against the full active rule set with the draft
    substituted in. No writes. Validates regex first.
  - `record_rule_change(db, action, before, after, ...)`: reapplies rules and persists a
    `RuleChangeReport` + `RuleChangeItem`s. Used by create/update/delete/toggle and
    "recategorize all" (action=`recategorize`).
  - `rule_snapshot()` for before/after JSON; `validate_rule_regex()` raising
    `RuleValidationError` at construction (invalid regex never reaches match time).
- Tests: `test_categorizer.py` — pattern matrix (5 patterns), rule types, AND/OR
  (documents the ported quirk: primary must match, OR folds into `running=True`),
  context filters, priority tie-break, manual precedence untouched, no-match=None, tags,
  preview gains/losses/changes, invalid regex, change-report contents. `test_categorizer_perf.py`
  — 50k reapply < 10s (marked `slow`). +32 tests (110 total default).

## Key Decisions
- No-match now clears to `category=None` (spec) rather than legacy "other".
- Manual transactions are identified by `categorization_source == "manual"` and skipped
  by reapplication (GP2/FR4.5 edge case).
- Preview simulates the whole rule set with the draft substituted, giving accurate
  change diffs including reattribution to other rules on losses.

## Deviations
- OR-condition semantics preserved verbatim from legacy (a known quirk); tests document
  it rather than "fix" it, per GP1 (port, don't rewrite matching semantics).

## Files Changed
- src/abn_combined/core/categorizer.py
- tests/{test_categorizer,test_categorizer_perf}.py

## Verification
- `ruff check .` clean; `pytest` 110 passed; slow perf reapply 50k in ~3.9s (<10s).
