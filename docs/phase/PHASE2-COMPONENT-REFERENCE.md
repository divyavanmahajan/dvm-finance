# Phase 2: Component Reference & Visual Guide

This document provides a visual breakdown of each Phase 2 component and how it integrates with the existing UI.

---

## Component 1: Filter Count Badge

**Location:** On the "Filters" button in the filter row
**Visibility:** Only when `activeFilterCount > 0`
**Animation:** Pulses on button hover

### Markup
```html
<button type="button" class="btn btn-outline-primary position-relative"
        data-bs-toggle="offcanvas" data-bs-target="#advancedFiltersOffcanvas">
  Filters
  <span class="badge bg-danger position-absolute top-0 start-100 translate-middle"
        x-show="activeFilterCount > 0"
        x-text="activeFilterCount"
        style="display: none !important;">
  </span>
</button>
```

### Visual
```
┌─────────────────────────────────────────┐
│                                         │
│  Filters Button                    ┌─┐  │
│                                    │3│  │  ← Badge showing 3 active filters
│                                    └─┘  │
│                                         │
└─────────────────────────────────────────┘
```

### CSS Classes
- `.position-relative` — on button container
- `.badge` — styling
- `.position-absolute.top-0.start-100.translate-middle` — positioning (top-right corner)
- `.bg-danger` — red background (indicates active state)

### Alpine
- `x-show="activeFilterCount > 0"` — visibility toggle
- `x-text="activeFilterCount"` — dynamic count

---

## Component 2: Offcanvas Advanced Filters Panel

**Location:** Slides in from the right edge
**Breakpoints:** 100% width (mobile), 400px max-width (desktop)
**Interaction:** Opens via button toggle, closes via × button or Apply/Reset

### Markup Structure
```html
<div class="offcanvas offcanvas-end" id="advancedFiltersOffcanvas" tabindex="-1">
  <!-- Header -->
  <div class="offcanvas-header">
    <h5 class="offcanvas-title">Filters</h5>
    <button type="button" class="btn-close" data-bs-dismiss="offcanvas"></button>
  </div>

  <!-- Body (scrollable) -->
  <div class="offcanvas-body">
    <!-- Date Range Input Group -->
    <!-- Amount Range Input Group -->
    <!-- Account Select -->
    <!-- Categories Multi-Select -->
    <!-- Exclude Categories Multi-Select -->
    <!-- Tags Multi-Select -->
  </div>

  <!-- Footer with Actions -->
  <div class="offcanvas-footer border-top p-3 d-flex gap-2">
    <button type="button" class="btn btn-secondary flex-grow-1" @click="clearFilters()">
      Reset
    </button>
    <button type="button" class="btn btn-primary flex-grow-1" data-bs-dismiss="offcanvas">
      Apply
    </button>
  </div>
</div>
```

### Visual (Desktop & Mobile)

#### Desktop
```
┌──────────────────────────────┐
│ Transactions                 │
├──────────────────────────────┤
│ [Search] [Date] [Sort] [Filters] 3 │
└──────────────────────────────┘
           ↓ click Filters button
┌──────────────────────┬──────────────────────┐
│                      │  Filters         [X] │
│                      │  ──────────────────  │
│                      │ Date Range:          │
│                      │ [From] – [To]        │
│                      │                      │
│ (Transaction Table)  │ Amount Range (€):    │
│                      │ [€Min] – [€Max]      │
│                      │                      │
│                      │ Account:             │
│                      │ [Select]             │
│                      │                      │
│                      │ Categories:          │
│                      │ [Multi-select]       │
│                      │                      │
│                      │ Exclude Categories:  │
│                      │ [Multi-select]       │
│                      │                      │
│                      │ Tags:                │
│                      │ [Multi-select]       │
│                      │ ──────────────────  │
│                      │ [Reset]  [Apply]  │  ← Footer
│                      └──────────────────────┘
```

#### Mobile (full width)
```
┌────────────────────────────────┐
│ Transactions                   │
├────────────────────────────────┤
│ [Search] [Date] [Sort] [Filters]3│
└────────────────────────────────┘
                ↓
┌────────────────────────────────┐
│ Filters                      [X]│
├────────────────────────────────┤
│ Date Range:                    │
│ [From]         [To]            │
│                                │
│ Amount Range (€):              │
│ [€Min]     [€Max]              │
│                                │
│ Account:                       │
│ [Account Select]               │
│                                │
│ Categories:                    │
│ [Multi-select box]             │
│                                │
│ Exclude Categories:            │
│ [Multi-select box]             │
│                                │
│ Tags:                          │
│ [Multi-select box]             │
├────────────────────────────────┤
│ [Reset]        [Apply]         │
└────────────────────────────────┘
```

### Input Groups (Date & Amount)

```
Date Range:
┌─────────┬─┬─────────┐
│ 2026-01 │ │ 2026-12 │  ← Two date inputs joined by "–"
└─────────┴─┴─────────┘

Amount Range (€):
┌─┬──────────┬─┬──────────┐
│€│ 50.00 │–│€│ 200.00 │  ← Currency prefix + number inputs
└─┴──────────┴─┴──────────┘
```

### CSS Classes
- `.offcanvas.offcanvas-end` — slide from right
- `.offcanvas-header` — sticky header
- `.offcanvas-body` — scrollable content
- `.offcanvas-footer` (custom) — sticky footer with border-top
- `.input-group` — joined inputs for date/amount
- `.input-group-text` — currency prefix (€)
- `.form-select[multiple]` — multi-select for categories/tags

### Alpine Integration
- Button clicks: `@click="clearFilters()"` (Reset), `@click="submitForm()"` (Apply)
- Data binding via `form="filter-bar"` attribute — all inputs belong to main filter form

---

## Component 3: Active Filter Pills Strip

**Location:** Below filter bar, above transaction table
**Visibility:** Only when `activeFilters.length > 0`
**Animation:** Fade in/out smoothly

### Markup
```html
<div class="active-filters-strip" x-show="activeFilters.length > 0" style="display: none !important;">
  <div class="d-flex flex-wrap gap-2 align-items-center">
    <!-- Dynamic pills from Alpine loop -->
    <template x-for="filter in activeFilters" :key="filter.key">
      <span class="badge rounded-pill text-bg-primary d-flex align-items-center gap-2">
        <span x-text="`${filter.label}: ${filter.value}`"></span>
        <button type="button" class="btn btn-close btn-close-white"
                @click="removeFilter(filter.key)"
                :aria-label="`Remove ${filter.label}`">
        </button>
      </span>
    </template>
    
    <!-- Clear all button -->
    <button type="button" class="btn btn-sm btn-outline-secondary" @click="clearFilters()">
      Clear all
    </button>
  </div>
</div>
```

### Visual

#### With No Active Filters (hidden)
```
┌───────────────────────────────────────────┐
│ [Search] [Date] [Sort] [Filters]          │
└───────────────────────────────────────────┘
                    ↓ (no pills strip)
┌───────────────────────────────────────────┐
│                                           │
│ (Transaction Table Starts Here)           │
│                                           │
```

#### With Active Filters (visible)
```
┌───────────────────────────────────────────────────────┐
│ [Search] [Date] [Sort] [Filters] 2                    │
├───────────────────────────────────────────────────────┤
│ ┌──────────────────────────────┐  ┌───────────────┐  │
│ │ Date: 2026-01–2026-12   [x] │  │ Amount: €50–€ │  │  ← Dismissible pills
│ └──────────────────────────────┘  │ 200         [x] │
│                                  └───────────────┘
│ [Clear all]                                          │  ← Clear all button
├───────────────────────────────────────────────────────┤
│                                                       │
│ (Transaction Table)                                   │
│                                                       │
```

### Data Structure (Alpine)
```javascript
activeFilters = [
  { key: 'date_range', label: 'Date', value: '2026-01 – 2026-12' },
  { key: 'amount_range', label: 'Amount', value: '€50 – €200' },
  { key: 'account', label: 'Account', value: 'Main Account' },
  // ... more filters
]
```

### CSS Classes
- `.active-filters-strip` — container (blue info background)
- `.badge.rounded-pill.text-bg-primary` — pill styling
- `.d-flex.flex-wrap.gap-2` — layout (flexbox, wrapping, spacing)
- `.btn-close.btn-close-white` — close icon (white on blue)
- `.btn.btn-sm.btn-outline-secondary` — "Clear all" button

### Interactions
- **Click ×:** `@click="removeFilter(filter.key)"` → clears that filter + submits form
- **Click "Clear all":** `@click="clearFilters()"` → clears all filters + submits form
- **Alpine loop:** `x-for="filter in activeFilters"` — renders one pill per active filter

---

## Component 4: Empty State Card

**Location:** Replaces transaction table when no results match filters
**Visibility:** Only when `not page.total and chips` (no rows AND filters applied)
**Layout:** Centered, vertical stack

### Markup
```html
<div class="empty-state">
  <!-- Icon -->
  <div class="empty-state-icon">
    <i class="bi bi-inbox"></i>  ← Bootstrap Icons inbox icon
  </div>

  <!-- Heading -->
  <h2 class="empty-state-heading">No transactions match your filters</h2>

  <!-- Subtext with filter list -->
  <div class="empty-state-subtext">
    <p>You're filtering by:</p>
    <div class="empty-state-filters">
      <ul>
        <li>Date: 2026-01 – 2026-12</li>
        <li>Amount: €50 – €200</li>
        <li>Account: Main Account</li>
      </ul>
    </div>
    <p style="margin-top: 1rem;">Try adjusting your filters or clearing them entirely.</p>
  </div>

  <!-- Action button -->
  <button type="button" class="btn btn-primary" @click="clearFilters()">
    Clear all filters
  </button>
</div>
```

### Visual

```
┌─────────────────────────────────────────────────┐
│                                                 │
│                      📥                         │  ← Icon (large, muted)
│                                                 │
│    No transactions match your filters          │  ← Heading
│                                                 │
│         You're filtering by:                    │  ← Subtext
│         • Date: 2026-01 – 2026-12               │
│         • Amount: €50 – €200                    │
│         • Account: Main Account                 │
│                                                 │
│      Try adjusting your filters or clearing    │
│           them entirely.                        │
│                                                 │
│              [Clear all filters]                │  ← Action button
│                                                 │
└─────────────────────────────────────────────────┘
```

### CSS Classes
- `.empty-state` — container (light gray background, border, centered)
- `.empty-state-icon` — icon wrapper (large font, muted color)
- `.bi.bi-inbox` — Bootstrap Icons inbox icon
- `.empty-state-heading` — heading styling (font-size, font-weight)
- `.empty-state-subtext` — subtext color (muted) and line-height
- `.empty-state-filters` — filter list wrapper (border, padding, code-like styling)

### Responsive
- Mobile: Padding reduced, icon smaller, text smaller
- Desktop: Full padding, icon 4rem, responsive heading

---

## Data Flow Diagram

```
User Action → Alpine Event → Form Manipulation → HTMX Submit → Backend Filter → Response → Swap → Alpine Sync

1. User clicks "Filters" button
   └─→ Bootstrap Offcanvas opens (no Alpine needed)

2. User changes date_from input (in offcanvas)
   └─→ Form has hx-trigger="change from:input[type=date]"
   └─→ HTMX fires GET /transactions/table?date_from=...
   └─→ Backend queries transactions
   └─→ Returns _transactions_table.html partial
   └─→ HTMX swaps #txn-table div
   └─→ htmx:afterSwap event fires
   └─→ Alpine syncFiltersFromUrl() parses URL params
   └─→ Sets activeFilters = [...] and activeFilterCount = 2
   └─→ Pills strip becomes visible (x-show triggers)
   └─→ Badge updates with count "2"

3. User clicks × on "Date" pill
   └─→ @click="removeFilter('date_range')" fires
   └─→ Alpine clears date_from + date_to inputs
   └─→ Alpine calls submitForm() (manual HTMX trigger)
   └─→ Same flow as step 2 (HTMX submit → response → swap → sync)

4. User clicks "Clear all"
   └─→ @click="clearFilters()" fires
   └─→ Alpine loops through all form fields, clears each
   └─→ Alpine calls submitForm()
   └─→ Same flow as step 2
   └─→ URL becomes "/?", pills strip hidden, badge hidden
```

---

## Accessibility Features

### Keyboard Navigation
| Action | Key |
|--------|-----|
| Open/close offcanvas | Enter on "Filters" button |
| Close offcanvas | Escape |
| Navigate inputs | Tab / Shift+Tab |
| Focus search box | Ctrl+K (custom in phase2.js) |
| Remove pill | Enter on × button |

### Screen Readers
- All inputs have associated `<label>` elements
- Buttons have `aria-label` attributes
- Close button: `aria-label="Close advanced filters"`
- Remove pill: `aria-label="Remove Date filter"`
- Empty state: Semantic HTML (no aria-* needed)

### Visual Indicators
- Focus states: 2px outline on all interactive elements
- Hover states: Color shift on pills, button opacity change
- Disabled states: `.disabled` class, reduced opacity
- High-contrast mode: Border width increases

---

## Color Scheme

### Light Mode
- **Pills strip background:** `#e7f3ff` (light blue)
- **Pills:** `.badge.text-bg-primary` → blue background, white text
- **Close icon:** White on blue
- **Empty state background:** `#f5f5f5` (light gray)
- **Icons:** Muted gray (`#6c757d`)

### Dark Mode
```css
@media (prefers-color-scheme: dark) {
  .active-filters-strip { background: rgba(13, 110, 253, 0.15); }
  .empty-state { background: #212529; }
}
```

---

## Responsive Behavior

### Mobile (< 576px)
- Filter row stacks vertically
- Offcanvas takes 100% width
- Pills stack in single column
- Empty state padding reduced

### Tablet (576px – 992px)
- Filter row wraps (2–3 per line)
- Offcanvas max-width: 400px
- Pills wrap naturally
- Empty state responsive font

### Desktop (> 992px)
- Filter row single line
- Offcanvas fixed at 400px
- Pills inline with wrap
- Empty state full-width card

---

## Performance Considerations

### CSS
- `.active-filters-strip` uses conditional rendering (`x-show`), not `v-if`
  - Faster toggle (DOM stays, only display:none)
  - Trade-off: Slightly more bytes in HTML
- Animations use `@keyframes fadeIn` (GPU-accelerated)
- No shadows on scroll (light performance footprint)

### JavaScript
- `syncFiltersFromUrl()` runs on every HTMX swap (minimal cost, O(n) params)
- `removeFilter()` is O(1) per filter
- No debouncing needed (HTMX handles form changes)
- `phase2.js` is ~3KB minified

### Network
- Pills/badges are rendered server-side or via Alpine (no extra requests)
- Empty state is part of `_transactions_table.html` partial
- Offcanvas markup is in `transactions.html` (downloaded once)

---

## Summary

Phase 2 adds four polished components:
1. **Filter Count Badge** — notification on button
2. **Offcanvas Panel** — hidden filter controls
3. **Pills Strip** — active filter display + removal
4. **Empty State** — helpful message when no results

All components use Bootstrap 5.3 utilities + custom CSS, Alpine.js for state, and HTMX for form submission. Filter state always lives in the URL query params.
