# 09 — Tags, Budgets, Cash Flow

## Goal
Supporting tabs ported from abn-analyst: tag management, budget CRUD with budget-vs-actual, and the cash-flow summary — all as tables, no charts.

## Context
Spec FR5–FR6. Kept features with lower daily usage; straightforward ports onto the new UI stack.

## Prerequisites
06-transactions-view (uses effective-tag/category semantics and filter URLs).

## Tasks
1. Tags page: list all tags (rule-assigned + manual) with usage counts linking to `/transactions?tags=<tag>`; rename (updates rules' `tags` and both transaction tag columns, port `rename_category_or_tag` logic); delete with confirm.
2. Budgets page: CRUD for category/amount/period(year|month|week)/validity dates/notes; budget-vs-actual table for a selected period — actual spend from effective categories, over-budget rows highlighted; category cells link to filtered transactions.
3. Cash flow page: income vs expense per period (month default) with net row, account filter, same URL-state controls; amounts link to filtered transactions (sign-based filter may reuse `amount_min/max`).
4. TDD: rename-propagation unit tests (rules + both tag columns + manual precedence intact), budget-vs-actual computation tests (period windows, validity dates), cash-flow aggregation tests; route tests; browser verification + screenshots.

## Acceptance Criteria
- Renaming a tag/category updates every place it appears and is covered by tests.
- Budget-vs-actual numbers match a hand-computed fixture.
- `pytest` green, `ruff check .` clean, screenshots captured.

## Notes
- Legacy sources: `app/routes/tags.py`, `budgets.py`, `cash_flow.py`, `scripts/rename_category_or_tag.py`.
