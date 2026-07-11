# Phase 2: Bootstrap 5 Advanced Filters & Empty States

## Overview
Implement interaction-heavy components for the transactions filter interface:
1. **Offcanvas Advanced Filters Panel** — slides from right
2. **Active Filter Pills Strip** — dismissible badges showing active filters
3. **Filter Count Badge** — notification badge on the "Filters" button
4. **Clear / Reset Functionality** — buttons to clear all filters
5. **Empty State Card** — when no transactions match filters

## Key Architectural Decisions

### 1. Offcanvas Panel
- Bootstrap `.offcanvas.offcanvas-end` (consistent right-slide on all breakpoints)
- NOT a Bootstrap modal — offcanvas is lighter and better for side panels
- All filter inputs stay in the main `#filter-bar` form
- Offcanvas opens via `data-bs-toggle="offcanvas" data-bs-target="#advancedFilters"`
- Footer uses `border-top` to anchor Reset/Apply buttons

### 2. Active Filters State Management
- Alpine component `txnFilterBar()` tracks `activeFilters[]` array
- Each filter object: `{ key, label, value }` (e.g., `{ key: 'amount_min', label: 'Amount Min', value: '50' }`)
- Computed property `activeFilterCount` for badge display
- Removing a pill resets that form field + submits the form via HTMX

### 3. Filter Pills Strip
- Flex row with `.gap-2` for spacing
- Only renders when `activeFilters.length > 0`
- Each pill: `.badge.rounded-pill.text-bg-primary`
- Close button: `.btn-close` styled for inline use
- "Clear all" button at end calls `clearFilters()`

### 4. Empty State
- Centered card with Bootstrap utilities
- Shows `.bi.bi-inbox` icon (large, muted)
- Heading "No transactions match your filters"
- Subtext lists current active filters
- "Clear filters" button with `@click="clearFilters()"`

### 5. Filter Count Badge
- Absolutely positioned on "Filters" button: `.badge.bg-danger.position-absolute.top-0.start-100.translate-middle`
- Only visible when `activeFilterCount > 0` (use `x-show`)
- Updates dynamically as form changes

## File Structure
```
src/abn_combined/web/
├── templates/
│   ├── transactions.html          (modified — adds offcanvas markup)
│   ├── _advanced_filters.html     (new — offcanvas panel content)
│   ├── _active_filters_strip.html (new — pills strip)
│   └── _empty_state.html          (new — empty state card)
├── static/
│   ├── app.css
│   ├── phase2.css                 (new — offcanvas, pills, empty state styling)
│   └── js/
│       ├── transactions.js        (modified — Alpine component expansion)
│       └── phase2.js              (new — filter management logic)
```

## HTMX Integration
- Form `#filter-bar` remains unchanged; offcanvas inputs are part of this form
- `hx-include="#filter-bar"` captures all form fields (date, amount, account, categories, etc.)
- Removing a pill: `hx-get="/transactions/table?..." hx-target="#txn-table"`
- Form submission: same target and URL push

## Bootstrap Versions
- **v5.3+** (latest stable with minimal JQuery, uses native JS)
- Requires `bootstrap.bundle.min.js` in vendor (includes Popper.js)
- Offcanvas has solid browser support (95%+)

## Testing Notes
- Pills strip visibility: ensure `activeFilters.length > 0` gates rendering
- Badge visibility: `activeFilterCount > 0` hides badge when count is 0
- Empty state: test with `hx-get="/transactions/table" hx-swap="innerHTML"` returning no rows
- Removing filters: pill click should reflect in URL query params

## Golden Principles Alignment
- **#8 (Filter state in URL):** Pills and empty state auto-generate from URL params
- **Manual edits never overwritten:** Alpine syncs to form fields, not vice versa
- **No build step:** Alpine CDN + Bootstrap CSS only
