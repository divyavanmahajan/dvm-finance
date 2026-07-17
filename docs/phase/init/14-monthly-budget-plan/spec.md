# Monthly Budget Plan — Specification

## Overview

Replaces the current flat `budgets` table (one independent row per
category+period, recurring forever, no rollover, no whole-picture view) with
a **monthly budget plan**: one plan per calendar month, seeded from recent
actual spending via the existing Trends aggregation, showing planned income,
planned expenses, and leftover at a glance alongside per-category detail.
Desktop-only for this phase; iOS's read-only `BudgetRecord` schema mirror is
explicitly out of scope here and tracked as a required follow-up so its
snapshot round-trip isn't silently broken.

## Problem Statement

Today's `/budgets` page is a table of independent category limits added one
at a time via a free-text form. There is no way to see whether a month's
plan adds up as a whole (income vs. total planned vs. total actual), no
rollover of unspent/overspent amounts, and setting up a new period means
re-typing every category from memory. For the single household user of this
app, that's bookkeeping busywork, not a usable budgeting workflow.

## Goals

- Creating a new month's plan takes "review and adjust a few numbers," not
  "remember and retype every category."
- One glance at a month shows: planned income, planned expenses, planned
  leftover, and actual-so-far leftover.
- Per category, the plan shows the recommended amount (recent 3-month
  average) as ongoing context next to whatever was actually planned, even
  after editing.
- Unspent or overspent amounts can optionally roll into the next month, per
  category.
- Nothing about a category's real spending is invisible: categories with
  actual spend but no plan line surface in an explicit "Unbudgeted" section.
- No existing budget data is silently dropped by the migration.

## Non-Goals

- No charts/graphs (project-wide rule — text and tables only).
- No iOS budgets UI or iOS schema/snapshot updates in this phase (tracked
  separately below as required follow-up work).
- No weekly budgets going forward (see Constraints — existing week-period
  budgets are dropped by the migration, logged, not converted).
- No continuous re-seeding of a month's planned amounts after creation — the
  3-month-average shown alongside a planned amount is live context for the
  user to compare against, not an auto-adjusting value.
- No multi-currency budget support (matches existing single-currency
  assumption elsewhere in the app).
- No authentication/multi-user budget ownership (app is single-user local,
  per project-wide constraint).

## Users & Context

Single local user managing their own household finances through the
existing FastAPI + htmx/Alpine web UI, already familiar with the
Transactions/Trends screens' filter and click-through conventions. They
review budgets periodically (roughly monthly), not continuously.

## Requirements

### Functional Requirements

1. **Schema**: new `budget_plans` table (`id`, `month` — `YYYY-MM`, unique —
   `planned_income` nullable numeric, `created_at`, `updated_at`) and
   `budget_plan_items` table (`id`, `plan_id` FK, `category` — flat string,
   hierarchical prefix-matched exactly like today's effective-category
   matching — `planned_amount`, `rollover_enabled` bool default false,
   `notes`). Unique index on `(plan_id, category)`. The old `Budget` model
   and `budgets` table are removed.
2. **Migration**: an Alembic migration that
   - Creates the new tables.
   - For each existing `period="month"` budget, creates (or reuses) a
     `budget_plans` row for the month containing `start_date` (or the
     current month if `start_date` is null) and a corresponding
     `budget_plan_items` row.
   - For each existing `period="year"` budget, divides `amount` by 12 and
     applies that as `planned_amount` for the category in every month of the
     current calendar year's plan (creating those plans if they don't
     already exist from a month-period budget).
   - Drops `period="week"` budgets without converting them.
   - Writes a migration summary (counts of month-converted /
     year-converted / week-dropped rows) to migration output (e.g. via
     `op.execute`/`print` during upgrade, or a logged report) so nothing
     vanishes without a trace.
   - Is a one-way migration (no `downgrade` data reconstruction beyond
     schema drop — matches existing migration conventions in this repo;
     confirm against `alembic/versions/` precedent during implementation).
3. **Recommendation engine**: reuse `core/trends.py`'s aggregation (not a
   new parallel implementation) to compute, for a given target month, the
   average actual spend per effective category over the last 3 *full*
   calendar months before it, with the same transfer-exclusion and
   manual-category-precedence semantics `budget_report.py:compute_actual`
   already uses. Planned income is computed the same way, restricted to
   income-category actuals (categories your existing income detection
   already recognizes — confirm the exact predicate during implementation;
   likely the inverse of transfer/expense sign convention already used
   elsewhere).
4. **New-month creation flow**:
   - Entry point: "Create next month" action from the budget plan view,
     defaulting the target month to one past the latest existing plan (or
     the current month if no plans exist yet).
   - System computes, per category with either actual spend in the lookback
     window or an existing plan item in the immediately preceding month's
     plan, a suggested `planned_amount` (3-month average, see above).
   - For categories with `rollover_enabled=true` on their immediately
     preceding month's plan item, add `(previous planned_amount − previous
     actual)` to the suggested amount — this can be negative (overspend
     reduces the next suggestion) as well as positive.
   - Suggested `planned_income` computed the same way (3-month average of
     income actuals; income does not participate in rollover in this
     phase — out of scope unless raised again).
   - Present an editable review screen (not an immediate save) with every
     suggested category/amount pre-filled, editable, and removable, plus
     the ability to add a category with no recent history. User must
     explicitly submit to create the plan.
5. **Monthly plan view** (`/budgets?month=YYYY-MM` or equivalent
   URL-encoded state, per project convention of filter state living in the
   URL):
   - Summary bar: planned income, total planned expenses (sum of
     `planned_amount` across items), planned leftover
     (`planned_income − total planned expenses`), actual-so-far leftover
     (actual income so far this month − actual expenses so far this month).
   - Category table grouped by first-hyphen-segment parent, matching the
     Trends matrix rollup exactly (reuse or mirror `TrendsBuilder`'s
     grouping logic rather than reimplementing it) — expandable
     parent/children.
   - Each row: category, planned amount (inline-editable via htmx partial
     swap, no full page reload), recent-3-month-average shown as muted
     context text next to the planned amount (always visible, not just at
     creation), actual so far this month, remaining
     (`planned − actual`), status badge (`over` / `near` ≥80% / `under`,
     reusing `budget_status` thresholds), rollover toggle.
   - "Unbudgeted" section: categories with actual spend in the current
     month but no `budget_plan_item`, so nothing is hidden.
   - Month navigation: previous/next links; "Create next month" action
     triggers the flow in requirement 4 when the next month doesn't exist
     yet.
   - Category and amount cells link through to filtered Transactions,
     matching today's budget-vs-actual click-through behavior.
6. **API**: replace `api/budgets.py`'s CRUD-per-row endpoints with
   plan-oriented endpoints: `GET /budgets` (current/selected month view),
   `POST /budgets/plans` (create a month, given reviewed items from
   requirement 4), `PATCH /budgets/plans/{id}/items/{item_id}` (inline edit
   of a single planned amount or rollover flag, htmx partial response),
   `DELETE` for removing a category line from a plan.
7. **Templates**: rework `web/templates/budgets.html`,
   `_budgets_table.html`, `budgets_edit.html` (or replace with new
   plan-specific partials) to implement the grouped/seeded month view
   above, dropping the old single-category free-text add form.
8. **Snapshot format**: update `core/snapshots.py` schema export/import —
   `budgets` key in the snapshot JSON is replaced with `budget_plans`
   (each entry: `month`, `planned_income`, and nested `items: [{category,
   planned_amount, rollover_enabled, notes}]`). Identity for merge/import
   purposes becomes `(month)` for a plan and `(month, category)` for an
   item — the machine-local `id` is not exported, matching the existing
   convention for other entities. Bump `schema_version` to 2 given the
   shape change (confirm exact versioning/back-compat approach against
   existing snapshot import handling for older schema versions during
   implementation — decide whether schema_version 1 snapshots' old
   `budgets` key is still importable read-only or rejected outright).
9. **Documentation**: update `docs/product.md`'s Budgets mention and
   `docs/architecture.md`'s snapshot format section (the JSON shape example
   and the `budgets` identity bullet) to describe the new model. Update
   `docs/core-beliefs.md` only if a new invariant is introduced (e.g. "a
   month's plan, once created, is never re-seeded automatically").
10. **iOS follow-up (tracked, not built in this phase)**: file an explicit
    task/issue noting that `ios/DVMFinanceKit/Sources/DVMFinanceKit/Database/BudgetRecord.swift`
    and any iOS snapshot decode path still expect the old flat shape, and
    that importing a snapshot exported after this change will lose or fail
    to parse budget data on iOS until that record and its snapshot codec
    are updated to the new `budget_plans`/`budget_plan_items` shape. This
    phase does not touch iOS code.

### Non-Functional Requirements

- No charts/graphs; text and tables only, consistent with project-wide
  convention.
- No JS build step; htmx/Alpine only, consistent with the rest of the app.
- Filter/view state (selected month) lives in the URL query string, matching
  the Transactions/Trends convention.
- All new SQL/aggregation logic added for the recommendation engine and
  monthly view must respect the existing transfer-exclusion and
  manual-category-precedence conventions used everywhere else (no
  divergent semantics for budgets specifically).
- Migration must be safe to run against a database with zero, some, or many
  existing `budgets` rows without manual pre-cleanup.

## Architecture

No new services or major architectural components — this is additive within
the existing FastAPI + SQLAlchemy + Alembic + Jinja2/htmx/Alpine + SQLite
stack. New pieces:

- `core/models.py`: `BudgetPlan`, `BudgetPlanItem` SQLAlchemy models
  (replacing `Budget`).
- `core/budget_report.py`: reworked to compute plan-vs-actual for a given
  month's `BudgetPlan` (replaces the old period-window `budget_vs_actual_table`)
  plus a new recommendation function (e.g. `recommend_plan_items(db, target_month)`)
  that calls into `core/trends.py`'s existing aggregation rather than
  duplicating category/date-window SQL.
- `api/budgets.py`: reworked routes per Functional Requirement 6.
- `web/templates/budgets.html` + partials: reworked per Functional
  Requirement 7.
- `alembic/versions/`: one new migration per Functional Requirement 2.
- `core/snapshots.py`: updated export/import per Functional Requirement 8.

## Deployment

No change to deployment — this remains a local single-user app run via
`uvx abn-combined`; no Docker (project-wide constraint), no new
infrastructure or external services.

## User Flows

**Creating the first plan (no existing plans):**
1. User opens Budgets; sees an empty state with "Create this month's plan".
2. Clicks it → review screen shows suggested categories/amounts computed
   from the last 3 full months of actual data (if fewer than 3 months of
   history exist, average over whatever's available; if none, an empty
   plan with no suggestions and a note that there's not enough history
   yet).
3. User edits amounts, adds/removes categories, sets planned income, toggles
   rollover on a couple of categories, submits.
4. Lands on the new month's plan view.

**Rolling into the next month:**
1. From an existing month's plan view, user clicks "Create next month".
2. Review screen shows suggestions per Functional Requirement 4, including
   rollover adjustments for any category flagged in the current month.
3. User adjusts, submits, lands on the new plan.

**Reviewing mid-month:**
1. User opens Budgets, sees current month by default.
2. Summary bar shows planned vs. actual leftover; category table shows
   per-category status badges; user clicks an over-budget category's actual
   amount to jump to filtered Transactions for that category this month.

**Editing a planned amount:**
1. User clicks/taps a planned-amount cell inline, types a new value.
2. htmx partial swap updates that row's remaining/status/summary bar totals
   without a full page reload.

## Authentication and Authorization

No change — app remains single-user, local, no auth layer (project-wide
constraint).

## Data & Integrations

- Reads: `transactions` table (via existing effective-category/effective-tag
  SQL conventions), `core/trends.py` aggregation.
- Writes: new `budget_plans`/`budget_plan_items` tables.
- Snapshot export/import: see Functional Requirement 8.
- No external services or APIs involved.

## Edge Cases & Error Handling

- **Fewer than 3 months of transaction history**: recommendation engine
  averages over however many full months exist; if zero, suggests nothing
  and the review screen shows an explanatory empty state rather than an
  error.
- **Category renamed or newly appearing**: a category with no match in the
  lookback window simply gets no suggested amount; user can still add it
  manually on the review screen. No special rename-tracking is introduced
  for budgets (out of scope; matches existing category-string identity
  convention used elsewhere).
- **Duplicate month creation**: attempting to create a plan for a month that
  already exists is rejected (the "Create next month" action is only
  offered for the immediate next month past the latest plan; direct
  API/URL attempts at an existing month return a clear error, not a
  silent overwrite).
- **Negative planned amounts from rollover overspend**: allowed and
  displayed as-is (e.g. "planned: -€20" after a bad month) rather than
  clamped to zero — the user asked for symmetric rollover; the UI should
  make a negative planned amount visually obvious (e.g. same over/under
  badge styling extended, or a distinct visual treatment — decide exact
  styling during implementation, no new color/status vocabulary beyond
  existing over/near/under unless needed).
- **Migration with overlapping month/year budgets for the same category**:
  if both a month-period and a year-period (post ÷12) budget exist for the
  same category in the same target month, the month-period value takes
  precedence (more specific wins) rather than summing or erroring; log the
  conflict.
- **Snapshot import of an old-format snapshot** (schema_version 1, old
  `budgets` key): decide during implementation whether this is rejected
  with a clear error or best-effort converted using the same
  month/year/week rules as the Alembic migration; whichever is chosen must
  not silently drop data without a report, consistent with Goal "no
  existing budget data is silently dropped."

## Constraints & Assumptions

- Single currency, matching the rest of the app.
- Month-only granularity going forward; week-period budgets are
  intentionally dropped by migration per explicit user decision, not
  preserved in any form.
- iOS is explicitly out of scope for implementation in this phase (tracked
  follow-up only, Functional Requirement 10).
- No new authentication, no Docker, no charts, no JS build step, no LLM/MCP
  — all pre-existing project-wide constraints from `docs/core-beliefs.md`
  apply unchanged.
- Assumes `core/trends.py`'s aggregation can be called with an arbitrary
  target date window (last 3 full months before a given month) without
  modification, or with a small, backward-compatible extension if not —
  confirm during implementation.

## Testing

TDD (red/green) for:
- `BudgetPlan`/`BudgetPlanItem` model + migration: round-trip creation,
  unique constraints, migration conversion of existing month/year/week
  fixtures (assert exact converted amounts and dropped-row counts).
- Recommendation engine: 3-month-average computation against hand-computed
  fixtures (including the <3-months-of-history case and the zero-history
  case), rollover math (positive and negative), income suggestion.
- `budget_report.py` plan-vs-actual computation for a given month: status
  badge thresholds, "Unbudgeted" detection, summary bar totals.
- API routes: create-plan review/submit flow, inline PATCH edit, duplicate-
  month rejection, snapshot export/import round-trip for the new shape
  (including at least one cross-machine merge scenario matching existing
  snapshot test conventions).
- Route/browser-level tests + screenshots for the new templates, per
  existing project convention (`pytest -m e2e` / Playwright harness).
- Regression check: existing Transactions/Trends/snapshot tests for other
  entities (rules, rule_change_reports) remain green — no incidental
  breakage from the `budgets` key removal in the snapshot schema.

## Open Questions

- Exact snapshot `schema_version` back-compat policy for old-format
  `budgets` payloads (reject vs. best-effort convert) — flagged in Edge
  Cases, needs a decision during implementation, not blocking spec
  approval.
- Exact income-category detection predicate for planned-income suggestion —
  confirm against whatever convention (if any) already distinguishes
  income from expense categories elsewhere in the codebase.
- Visual treatment for negative planned amounts (rollover overspend) —
  no new design system vocabulary should be invented without checking
  existing badge/status styling first.
- iOS follow-up phase is filed but not scheduled — timing left to the user.

## Success Metrics

- A user can create a new month's plan in well under a minute for a
  household with an established spending history (suggestions pre-filled,
  minimal typing).
- The summary bar answers "am I on track this month" without the user
  doing any mental arithmetic across rows.
- Zero existing budget rows are unaccounted for after migration (every row
  is either converted, or explicitly logged as dropped per the agreed
  week-period rule).
- `pytest` green, `ruff check .` clean, e2e screenshots captured, matching
  existing phase acceptance-criteria conventions.
