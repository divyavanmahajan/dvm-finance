# 04 — Rule Engine, Preview, and Change Reports

## Goal
The categorization engine applies rules by priority with full condition/filter semantics, can compute a dry-run preview for a draft rule, and records a `RuleChangeReport` for every rule mutation or recategorization.

## Context
This is the heart of the app (spec FR4) and the feature the user cares most about: safe, auditable rule changes. Pure backend module — UI comes in step 07.

## Prerequisites
03-parsers-and-dedup.

## Tasks
1. Port matching logic from `abn-analyst/app/analyzer.py` (rule-based part only — no LLM/LlamaIndex/LangChain): rule types keyword/account_iban/structured_field/full_description; patterns contains/exact/starts_with/ends_with/regex; `field_target` resolution incl. structured-description fields; normalization via `normalize_string_for_matching`; context filters (account, currency, date range); additional `RuleCondition`s with AND/OR and sort order; priority order (lower wins, first match assigns category+tags).
2. `apply_rules(db, transaction_ids=None)`: sets `category`, `tags`, `categorization_source=str(rule.id)` on matching transactions; never touches `manual_category`/`manual_tags`; transactions with no match get category None (effective "Uncategorized").
3. `preview_rule(db, draft_rule, existing_rule_id=None)`: dry-run returning (a) transactions the draft matches, (b) diff vs current state — gains, losses (matched by old version, not by new), and category/tag changes. No writes.
4. Change reports: a `record_rule_change(db, action, before, after)` service that runs reapplication and persists `RuleChangeReport` + `RuleChangeItem`s (old→new category/tags per affected transaction). Used by create/update/delete/toggle and by "recategorize all" (FR4.7).
5. Regex validation at rule construction (invalid pattern → validation error, never a match-time 500).
6. TDD: port existing analyzer rule tests, then a matrix of unit tests — each rule_type × match_pattern, AND/OR conditions, context filters, priority tie-breaks, manual precedence untouched, preview gains/losses, change-report contents, invalid regex.
7. Benchmark-style test: 50k synthetic transactions reapplied < 10 s (NFR3) — mark `slow`.

## Acceptance Criteria
- Full matching-semantics test matrix green; behavior identical to abn-analyst for ported cases.
- Every rule mutation path produces a persisted report with correct per-transaction diffs.
- `pytest` green, `ruff check .` clean.

## Notes
- > ⚠ Golden Principle 2: manual edits are sacred — reapplication must never overwrite manual values.
- > ⚠ Golden Principle 5: no silent recategorization — every mutation goes through `record_rule_change`.

## External References
- Source: `/Users/divya/projects/abn-analyst/app/analyzer.py` (rule engine parts), `/Users/divya/projects/abn-analyst/app/routes/categorization_rules.py`.
