# Post-merge fixes — 2026-07-08

Branch: `fix/real-world-feedback`

## Orchestrator changes (context)

The orchestrator committed six code changes before this pass:

| File | Change |
|------|--------|
| `core/utils.py` | Added `CATEGORY_SEPARATOR = "-"` (real data confirmed hyphen, not colon) |
| `core/filters.py` | Category prefix matching via `CATEGORY_SEPARATOR`; new `exclude_categories` field + chips + `_removed` support |
| `core/trends.py` | Imports `CATEGORY_SEPARATOR` from `utils` |
| `core/budget_report.py` | Child-match uses `CATEGORY_SEPARATOR` only (dropped old `:%-` fallback) |
| `api/transactions.py` | `_known_categories` adds ancestor prefixes so subtrees are selectable |
| `web/templates/transactions.html` | New "Exclude ▾" checkbox dropdown |
| `cli.py` | `migrate-legacy` now also accepts `--data-dir` after the subcommand |
| `downloaders/paypal.py` | `identify_cdp_endpoint()` + `_connect_failure_message()` with targeted "other app on 9222" explanation |

## Import-order fixes (ruff I001)

`core/budget_report.py` and `core/filters.py` had `.utils` imported before `.models`; `core/trends.py` lacked a blank line between the import block and the first constant. Fixed to satisfy `ruff check`.

## Tests added / updated

### test_filters.py
- `test_multi_categories_including_uncategorized` — updated `food:groceries` → `food-groceries` (hyphen)
- **New** `test_exclude_categories_roundtrip`
- **New** `test_exclude_categories_in_query_string`
- **New** `test_exclude_category_from_params`
- **New** `test_exclude_category_chip_label`
- **New** `test_exclude_category_chip_remove`
- **New** `test_exclude_uncategorized_chip_label`

### test_transactions.py
- Fixtures: `income:salary` → `income-salary`, `food:restaurants` → `food-restaurants`
- Updated `test_filter_category_hierarchical` comment
- **New** `test_filter_exclude_category_subtree`
- **New** `test_filter_exclude_keeps_uncategorized` (NULL-safe exclusion)
- **New** `test_filter_include_exclude_combined`
- **New** `test_ancestor_prefixes_in_known_categories`

### test_budgets.py
- `seeded_db` fixture: `food:restaurants` → `food-restaurants`

### test_cli.py
- **New** `test_migrate_legacy_data_dir_after_subcommand`
- **New** `test_migrate_legacy_data_dir_before_subcommand`

### test_downloads.py
- **New** `TestConnectFailureMessage` class with three tests:
  - `test_browser_context_not_supported_with_browser_id`
  - `test_browser_context_not_supported_no_browser_id`
  - `test_generic_failure_message`

**Total: 462 passed (+15 new tests).**

## UI Bug fixes

### Bug 1 — Filter chips render as blank solid-blue pills

**Root cause:** `.chip` CSS used `background: var(--pico-primary-background)` which in Pico v2 is
the solid primary button blue. Text color `var(--pico-primary)` is the same hue → blue-on-blue.

**Fix (`web/static/app.css`):** Explicit light-blue tint `#ddeeff` / dark text `#1a3a6b` for
light mode; `@media (prefers-color-scheme: dark)` override with `#1e3a5f` / `#b8d4f5`.

### Bug 2 — Transaction detail row stuck on "Loading…"

**Root cause:** Transaction IDs contain CSS selector–special characters: `:` in PayPal IDs
(`pp:paypaleu_0AL232641L562823T`) and `.` in ABN amount-hashed IDs (`…_2000.0_…`).
`hx-target="#txn-detail-body-{id}"` calls `document.querySelector()` internally; the colon
was parsed as a CSS pseudo-class and the element was never found, so htmx discarded the response.

**Fix:**
- `app.py`: Added `_css_id()` Jinja2 filter (replaces `[^a-zA-Z0-9_-]` with `_`).
- `_transactions_row.html`: `{{ t.id | css_id }}` applied to both the `id` attribute of the
  detail body `<div>` and the `hx-target` selector on the expand button.

### Bug 3 — Rule not clickable from Source column

**Root cause:** Source column rendered plain text `rule #N`.

**Fix (`_transactions_row.html`):** Wrapped in `<a href="/rules/{{ t.categorization_source }}">`.

### Bug 4 — Clumsy filter bar layout

**Root cause:** Pico v2 sets `button { display: block; width: 100%; }` globally; Apply became a
full-width bar and Reset wrapped below it.

**Fix (`web/static/app.css`):** `.filter-row button, .filter-row a[role="button"] { width: auto; display: inline-flex; }`.

## Screenshots

Taken against the live app at `http://127.0.0.1:8123` with real migrated data.

| File | Shows |
|------|-------|
| `screenshots/a_filter_bar_expanded.png` | "More filters" expanded — tidy row, Apply/Reset side-by-side |
| `screenshots/b_filter_chips.png` | Readable chips: "Category: fixed-insurance ✕" and "Exclude: sweden-rent ✕" |
| `screenshots/c_transaction_detail.png` | Expanded transaction with all detail fields rendered |
| `screenshots/d_rule_link.png` | "rule #845" as a clickable blue link in the Source column |

## Docs updated

- `docs/product.md` — added mention of exclude-category filter capability
- `docs/architecture.md` — separator section updated: canonical `CATEGORY_SEPARATOR` from
  `core/utils.py`; removed outdated forward-compat `:` note
