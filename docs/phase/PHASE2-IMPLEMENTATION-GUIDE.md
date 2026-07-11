# Phase 2 Implementation Guide: Bootstrap 5 Advanced Filters & Empty States

## Overview
This guide walks through integrating Phase 2 components into the existing abn-combined app. Phase 2 adds four major UX improvements:
1. **Offcanvas Advanced Filters Panel** — hidden filters in a slide-out drawer
2. **Active Filter Pills Strip** — dismissible badges showing applied filters
3. **Filter Count Badge** — notification badge on the Filters button
4. **Empty State Card** — helpful message when no transactions match filters

## Prerequisites
- Bootstrap 5.3+ (with Popper.js for dropdowns and offcanvas)
- Alpine.js 3.x (for interactivity)
- HTMX (for form submission)
- Existing Phase 1 components (filter bar, transactions table)

## Files to Create/Modify

### New Files
```
src/abn_combined/web/static/
├── phase2.css              # Phase 2 styles
└── js/
    └── phase2.js           # Phase 2 Alpine component
```

### Modified Files
```
src/abn_combined/web/templates/
├── transactions.html       # Add offcanvas markup + pills strip
├── base.html               # Add Bootstrap + Popper CDN links
└── _transactions_table.html # Add empty state card when no results
```

---

## Step 1: Update base.html

Add Bootstrap CSS and Bundle JS to the `<head>` and before `</body>`:

```html
<!-- In <head> -->
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
<link rel="stylesheet" href="/static/app.css">
<link rel="stylesheet" href="/static/phase2.css">

<!-- Before </body> -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" defer></script>
<script src="/static/vendor/htmx.min.js" defer></script>
<script src="/static/vendor/alpine.min.js" defer></script>
<script src="/static/js/transactions.js" defer></script>
<script src="/static/js/phase2.js" defer></script>
```

**Rationale:** Bootstrap Bundle includes Popper.js (required for offcanvas positioning) and the offcanvas component. Bootstrap Icons provides the `.bi` classes for the empty state inbox icon.

---

## Step 2: Update transactions.html

Replace the entire `<form id="filter-bar">` with the new Phase 2 version from `phase2-transactions.html`.

### Key Changes
1. **Filter Bar Row 1:** Reorganized for Bootstrap grid (`.row.g-2`) with labeled inputs
2. **Filters Button:** Add `data-bs-toggle="offcanvas" data-bs-target="#advancedFiltersOffcanvas"`
3. **Filter Count Badge:** Positioned absolutely with `x-show="activeFilterCount > 0"`
4. **Hidden Advanced Inputs:** All advanced filters stay in the form (line 51 in phase2-transactions.html) but are hidden; the offcanvas *labels* these inputs, not duplicates them

### Form Structure
```html
<form id="filter-bar" ... x-data="txnFilterBar()">
  <!-- Visible filter row 1 (search, date preset, sort, filters button) -->
  
  <!-- Hidden advanced filter inputs (controlled by offcanvas) -->
  <div style="display: none;">
    <input name="date_from" ... />
    <input name="date_to" ... />
    <!-- All other advanced filters -->
  </div>
</form>
```

**Why hidden inputs?** HTMX's `hx-include="#filter-bar"` will capture all form fields, including the hidden ones. The offcanvas provides a UI to manipulate these hidden inputs.

---

## Step 3: Create & Link phase2.css

Place `phase2.css` in `/static/` and link it in `base.html` (step 1).

**What it styles:**
- `.offcanvas` — responsive width (100% mobile, 400px desktop)
- `.offcanvas-footer` — custom Bootstrap footers (not built-in; uses flex + border-top)
- `.active-filters-strip` — blue info box with pills
- `.badge.rounded-pill` — filter pill styling with inline close buttons
- `.empty-state` — centered card with icon, heading, subtext
- Dark mode support via `@media (prefers-color-scheme: dark)`
- Accessibility: high-contrast mode, focus states

---

## Step 4: Create & Link phase2.js

Place `phase2.js` in `/static/js/` and link in `base.html` (step 1).

**What it does:**
```js
// Initialize on DOM ready
window.Alpine.data('txnFilterBar', () => ({
  activeFilters: [],      // Array of {key, label, value}
  activeFilterCount: 0,   // Computed count for badge display

  init() {
    this.syncFiltersFromUrl();    // Build activeFilters from URL params
    this.autoExpandAdvancedIfNeeded(); // Show advanced row if filters active
  },

  removeFilter(key) { /* Clear one filter + resubmit */ },
  clearFilters() { /* Clear all + resubmit */ },
  submitForm() { /* Trigger HTMX form submission */ },
  syncFiltersFromUrl() { /* Parse URL params into activeFilters array */ }
}));
```

**Key functions:**
- `syncFiltersFromUrl()` — parses `?date_from=2026-01-01&amount_min=50` etc. into readable filter labels
- `removeFilter(key)` — clears one filter from the form and resubmits
- `clearFilters()` — resets all filter inputs and resubmits
- `submitForm()` — manually triggers the HTMX form submission (used by remove/clear)

---

## Step 5: Update _transactions_table.html

Add the empty state card at the top of the file, replacing or alongside the existing "No transactions match these filters" message:

```html
{% if not page.total and chips %}
<div class="empty-state">
  <div class="empty-state-icon">
    <i class="bi bi-inbox"></i>
  </div>
  <h2>No transactions match your filters</h2>
  <div class="empty-state-subtext">
    <p>You're filtering by:</p>
    <div class="empty-state-filters">
      <ul>
        {% for chip in chips %}
        <li>{{ chip.label }}</li>
        {% endfor %}
      </ul>
    </div>
  </div>
  <button type="button" class="btn btn-primary" @click="clearFilters()">
    Clear all filters
  </button>
</div>
{% endif %}
```

(See `_empty_state.html` for the full template.)

---

## Step 6: Update transactions.js

Expand the existing `txnFilterBar()` component to include Phase 2 logic. Merge the code from `phase2.js` into `transactions.js`, or keep them separate and link both scripts.

**If keeping separate:** Link both in `base.html`:
```html
<script src="/static/js/transactions.js" defer></script>
<script src="/static/js/phase2.js" defer></script>
```

**If merging:** Copy the entire Alpine component definition from `phase2.js` into `transactions.js`, replacing the simpler version.

---

## Integration Checklist

- [ ] Bootstrap 5.3+ CDN links in `base.html` (CSS + Bundle JS)
- [ ] Bootstrap Icons CDN in `base.html`
- [ ] `phase2.css` linked in `base.html`
- [ ] `phase2.js` linked in `base.html` (or merged into `transactions.js`)
- [ ] `transactions.html` updated with:
  - [ ] New filter row layout (grid-based)
  - [ ] Filters button with offcanvas toggle
  - [ ] Offcanvas panel markup
  - [ ] Active filters strip (with `x-show="activeFilters.length > 0"`)
  - [ ] Hidden advanced filter inputs (stay in form for HTMX)
- [ ] `_transactions_table.html` updated with empty state card
- [ ] Form `id="filter-bar"` remains (HTMX target)
- [ ] All form inputs have `name` attributes for HTMX serialization

---

## How It Works: Data Flow

### User clicks "Filters" button
1. Button has `data-bs-toggle="offcanvas" data-bs-target="#advancedFiltersOffcanvas"`
2. Bootstrap offcanvas JS shows the panel

### User changes a filter input (e.g., date_from)
1. Form has `hx-trigger="... change from:input[type=date]"`
2. HTMX detects the change and fires `GET /transactions/table`
3. HTMX includes all form fields via `hx-include="#filter-bar"`
4. Backend filters transactions and returns `_transactions_table.html` partial
5. HTMX swaps the `#txn-table` div with the new partial
6. URL is pushed via `hx-push-url="true"` (e.g., `/?date_from=2026-01-01`)
7. Alpine `syncFiltersFromUrl()` runs on `htmx:afterSwap` and updates `activeFilters[]`
8. Pills strip becomes visible (if activeFilters.length > 0)
9. Badge shows the count

### User clicks the "×" on a pill
1. `@click="removeFilter('date_from')"` fires
2. Alpine finds the input and clears it: `input.value = ''`
3. Alpine calls `submitForm()` which triggers HTMX again
4. Same flow as above: filter, display, update URL, sync Alpine

### User clicks "Clear all"
1. `@click="clearFilters()"` fires
2. Alpine loops through all inputs and clears them
3. Calls `submitForm()` to resubmit

---

## Styling Notes

### Light & Dark Modes
- `.active-filters-strip` has a blue info background in light mode, darker blue in dark mode
- `.empty-state` background changes to match theme
- All colors use CSS custom properties (`--bs-*`) for theme consistency

### Responsive Design
- Offcanvas width is 100% on mobile, 400px on desktop
- Pills strip wraps on small screens
- Filter inputs stack vertically in the offcanvas

### Accessibility
- All form inputs have labels (screen readers)
- Close buttons have `aria-label` attributes
- High-contrast mode support via `@media (prefers-contrast: more)`
- Focus states are visible

---

## Testing Checklist

### Unit Tests (Playwright e2e)
- [ ] Click "Filters" button → offcanvas opens
- [ ] Enter date range → HTMX request fires → pills strip shows
- [ ] Click "×" on pill → filter removed, pills strip updates
- [ ] Click "Clear all" in pills → all filters cleared
- [ ] No filters active → pills strip hidden, badge hidden
- [ ] Empty transaction state → empty state card shows
- [ ] Click "Clear filters" on empty state → filters cleared + table reloads

### Manual Tests
- [ ] Offcanvas responsive (mobile: full width, desktop: 400px)
- [ ] Dark mode: colors adjust correctly
- [ ] Keyboard: Escape closes offcanvas, Ctrl+K focuses search
- [ ] Browser back/forward: URL syncs with filters

---

## Common Pitfalls

### 1. Hidden Inputs Not Captured
**Problem:** Form submits but advanced filters aren't included.
**Solution:** Ensure hidden `<div style="display: none;">` contains all advanced filter inputs. HTMX will still serialize them.

### 2. Offcanvas Doesn't Close After Apply
**Problem:** User clicks Apply but panel stays open.
**Solution:** Add `data-bs-dismiss="offcanvas"` to the Apply button, OR call `bootstrap.Offcanvas.getInstance(el).hide()` in Alpine.

### 3. Pills Strip Flashes
**Problem:** Pills appear then disappear momentarily.
**Solution:** Use `x-cloak` directive to hide Alpine elements until Alpine is ready: `<div x-show="..." x-cloak>`

### 4. Badge Shows NaN or Wrong Count
**Problem:** `activeFilterCount` is not a number.
**Solution:** In `syncFiltersFromUrl()`, ensure you're incrementing a counter, not setting a string. Use `filters.length`.

### 5. Form Doesn't Submit After Clearing
**Problem:** User clicks "Clear all" but nothing happens.
**Solution:** In `clearFilters()`, ensure `submitForm()` is called and HTMX is configured on the form.

---

## Future Enhancements (Phase 3+)

- **Category dropdown:** Replace `<select multiple>` with a custom Alpine dropdown for better UX
- **Date picker:** Use a date picker library for range selection
- **Filter presets:** "This Month", "Last 30 Days" as quick buttons in offcanvas
- **Filter history:** Remember recently used filter combos
- **Export:** "Export filtered transactions" button

---

## Questions & Troubleshooting

### Q: Should I keep Pico CSS or switch to Bootstrap entirely?
**A:** Bootstrap 5.3 is a complete replacement. You can remove Pico from the CDN and use Bootstrap for all components. This Phase 2 assumes full Bootstrap adoption.

### Q: Can I use Bootstrap from npm instead of CDN?
**A:** Yes! Replace the CDN links with local bundle imports in `base.html`. The `package.json` would need `bootstrap` and `bootstrap-icons` added.

### Q: What if the user is on an older browser without offcanvas support?
**A:** Offcanvas has 95%+ browser support (iOS 13+, Chrome 90+). For older browsers, fall back to a modal or show/hide a div. Phase 2 assumes modern browsers.

### Q: How do I prevent the offcanvas from closing when the user interacts with inputs?
**A:** The offcanvas body is scrollable and separate from the header/footer. Don't use `data-bs-backdrop="static"` unless you want to prevent closing via backdrop click. Users can close via the X button or Apply button.

---

## Summary

Phase 2 adds a polished filter UX with Bootstrap offcanvas, active filter pills, count badges, and empty states. All filter state remains in the URL (Golden Principle 8), while Alpine.js provides snappy UI interactivity. The implementation is framework-agnostic, works with HTMX, and requires only Alpine 3.x + Bootstrap 5.3.
