# Phase 3: Bootstrap 5 Redesign — Quick Reference

## Deliverables

### 1. HTML Template
**File:** `docs/phase/phase3-transactions.html`

Complete transactions template with:
- Bootstrap 5.3 styled filter bar
- Responsive offcanvas advanced filters panel
- Alpine-controlled category checkbox-dropdown with search
- Active filter pills strip
- Placeholder for transaction table (uses `_transactions_table_phase3.html`)

**Status:** ✓ Ready to integrate

### 2. CSS Stylesheet
**File:** `src/abn_combined/web/static/phase3.css`

~700 lines of CSS providing:
- `.dropdown`, `.category-list`, `.form-check-input` styling for category picker
- `.pagination`, `.page-link`, `.page-item` for Bootstrap pagination
- Mobile table layout with `.txn-card`, `.txn-card-header`, `.txn-card-body`, etc.
- Responsive offcanvas filter panel (grid layouts at different breakpoints)
- Dark mode support for all components
- Responsive adjustments for sm/md/lg/xl/xxl breakpoints

**Status:** ✓ Ready to use

### 3. JavaScript Component
**File:** `src/abn_combined/web/static/js/phase3.js`

~200 lines of Alpine.js + HTMX integration:
- `categoryPicker()` Alpine component: manages category selection, search filtering, button text
- `paginationHandler()` Alpine component: page size changes, page navigation
- HTMX event handlers: smooth AJAX updates, loading indicators
- Utility functions: scroll-to-element, slugify

**Status:** ✓ Ready to use

### 4. Table Partial
**File:** `docs/phase/_transactions_table_phase3.html`

Responsive table partial with:
- **Desktop (md+):** Bootstrap table with existing row structure
- **Mobile (<md):** Stacked card layout with expandable details
- CSS-only layout switching (no separate HTMX endpoint needed)
- Bootstrap `.pagination .pagination-sm` component
- Active filter chips
- First-run hint + empty state

**Status:** ✓ Ready to integrate (copy to `src/abn_combined/web/templates/`)

### 5. Documentation
- `PHASE3_IMPLEMENTATION_NOTES.md` — Detailed technical documentation
- `PHASE3_INTEGRATION_GUIDE.md` — Step-by-step integration instructions
- `PHASE3_SUMMARY.md` — This file

---

## Key Features

### Component 1: Category Checkbox-Dropdown
```
┌─ Categories [v]────────────────────┐
│ 🔍 [Search categories…]            │
├────────────────────────────────────┤
│ ☐ Uncategorized                    │
│ ☑ Groceries (highlight if checked) │
│ ☐ Transport                        │
│ ☐ Utilities                        │
└────────────────────────────────────┘

Button text updates:
- "Categories" (none selected)
- "3 selected" (some selected)
- "All categories" (all selected)
```

**Features:**
- Real-time search filtering (Alpine `x-for` with `x-model`)
- Synchronized with hidden filter-bar checkboxes
- HTMX-triggered form submission on change
- `data-bs-auto-close="outside"` keeps dropdown open while checking

### Component 2: Bootstrap Pagination
```
Prev  1  2  3  4  5  …  10  Next
Page 3 of 10
```

**Features:**
- Smart ellipsis for large page counts
- Current page highlighted (`.page-item.active`)
- Previous/Next disabled at boundaries
- HTMX-wired page links (`hx-get`, `hx-push-url`)
- Preserves all filter state when navigating

### Component 3: Mobile Card Layout
```
┌─────────────────────────────┐
│ 2026-07-08  Amount: −€ 43.17│  Desktop: hidden
│ Albert Heijn 1653           │  Mobile:  shown
│ Category: Groceries         │
│ Account: NL91ABNA…          │
│ [Show detail]  [+ rule]     │
└─────────────────────────────┘
```

**Features:**
- CSS media queries switch layout at md breakpoint (768px)
- No separate HTMX endpoint needed
- Expandable detail section
- Money colors (positive: green, negative: red)
- Full responsive stack: xs → sm → md → lg → xl → xxl

---

## Integration Checklist

### Before Adding to Project

- [ ] Review `PHASE3_IMPLEMENTATION_NOTES.md`
- [ ] Verify Bootstrap 5.3 is in `base.html`
- [ ] Confirm HTMX and Alpine.js are loaded

### Files to Add/Update

- [ ] Add `src/abn_combined/web/static/phase3.css`
- [ ] Add `src/abn_combined/web/static/js/phase3.js`
- [ ] Add `src/abn_combined/web/templates/_transactions_table_phase3.html`
- [ ] Update `src/abn_combined/web/templates/base.html` (add phase3 assets)
- [ ] Update `src/abn_combined/web/templates/transactions.html` (use new components)

### Backend Checks

- [ ] `/transactions/table` endpoint returns `PageInfo` with `page`, `pages`, `total`, `has_prev`, `has_next`, `start_index`, `end_index`
- [ ] `FilterState` has `with_page(n)` and `to_query_string()` methods
- [ ] Endpoint accepts and properly handles `category` and `page` query params

### Testing

- [ ] Category picker search works
- [ ] Pagination links update table
- [ ] Mobile cards display on narrow screens
- [ ] Dark mode looks good
- [ ] All breakpoints tested (xs, sm, md, lg, xl, xxl)

---

## Breakpoint Reference

| Breakpoint | Width      | Use Case                           |
|------------|------------|------------------------------------|
| **xs**    | <576px     | Extra small phones                 |
| **sm**    | 576–768px  | Small phones                       |
| **md**    | 768–992px  | Tablets (table→cards switch here) |
| **lg**    | 992–1200px | Desktops                           |
| **xl**    | 1200–1400px| Large desktops (4-col grid here) |
| **xxl**   | 1400px+    | Extra large screens                |

**Phase 3 Uses:**
- `<md`: Mobile cards + stacked buttons
- `≥md`: Desktop table + inline buttons
- `≥xl`: Four-column filter grid

---

## CSS Classes Summary

### Category Picker
- `.dropdown` — Bootstrap dropdown container
- `.dropdown-toggle` — Button that opens menu
- `.dropdown-menu` — Menu container
- `.category-list` — Scrollable list of checkboxes
- `.dropdown-item` — Individual checkbox item
- `.form-check-input` — Checkbox input
- `.form-check-label` — Checkbox label

### Pagination
- `.pagination` — Container
- `.pagination-sm` — Smaller variant
- `.page-item` — Individual page/button
- `.page-link` — Clickable link
- `.page-item.active` — Current page
- `.page-item.disabled` — Inactive button/ellipsis

### Mobile Cards
- `.txn-cards-container` — Flex container for cards
- `.txn-card` — Individual card
- `.txn-card-header` — Date + amount
- `.txn-card-body` — Main content
- `.txn-card-row` — Label + value pair
- `.txn-card-detail` — Expandable details
- `.txn-card-footer` — Action buttons

### Utilities
- `.d-md-block` — Show on md+
- `.d-md-none` — Hide on md+
- `.w-100` — Full width
- `.flex-grow-1` — Flex grow
- `.gap-2` — Bootstrap gap utility

---

## Alpine.js Functions

### `categoryPicker(allCategories, initialSelected)`

**Properties:**
- `selected: []` — Array of selected category IDs
- `searchQuery: string` — Current search text
- `allCats: []` — All available categories

**Computed:**
- `filtered` — Categories matching search query

**Methods:**
- `buttonText()` → "Categories" | "N selected" | "All categories"
- `toggleCategory(id)` — Add/remove from selection
- `updateHiddenInputs()` — Sync to form checkboxes, trigger HTMX
- `clearCategories()` — Empty selection
- `slugify(text)` → HTML-safe ID string

**Usage:**
```html
<div x-data="categoryPicker({{ categories | tojson }}, {{ filter.categories | tojson }})">
  ...
</div>
```

---

## HTMX Integration

### Flow: Category Selection

```
User checks category checkbox
  ↓ (Alpine @change event)
updateHiddenInputs()
  ↓ (finds hidden inputs in filter-bar)
Sets checkbox.checked = true
  ↓ (htmx.trigger)
htmx:change event fires
  ↓ (filter-bar hx-trigger="change")
GET /transactions/table?category=X&page=1&...
  ↓ (server)
Returns _transactions_table_phase3.html partial
  ↓ (hx-swap="innerHTML")
Replaces #txn-table contents
  ↓ (hx-push-url="true")
Updates browser URL
  ↓ (htmx:afterSwap event)
Alpine.scan() reinitializes components
```

### Event Handlers (phase3.js)

```javascript
document.addEventListener('htmx:afterSwap', fn);   // Reinit Alpine
document.addEventListener('htmx:xhr:progress', fn); // Show loading
document.addEventListener('htmx:afterSettle', fn);  // Hide loading
```

---

## Golden Principle Compliance

**Golden Principle 8:** "Filter state lives in the URL"

**Phase 3 Implementation:**
✓ All filter selections (categories, dates, amounts, etc.) stored in query string
✓ Pagination state (page number) in query string
✓ Bookmarkable URLs restore full state
✓ No client-side state persistence (filters are read-only in Alpine)
✓ Server renders HTML based on query string only

**Example URL:**
```
/transactions?q=albert&preset=last-7-days&sort=date_desc&category=Groceries&category=Transport&page=2
```

---

## Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| Category dropdown doesn't stay open while clicking checkboxes | Missing `data-bs-auto-close="outside"` | Add to button |
| Pagination links don't work | HTMX not loaded | Verify `htmx.min.js` in base.html |
| Mobile cards don't show | `phase3.css` not loaded | Add `<link rel="stylesheet" href="/static/phase3.css">` |
| Category search returns nothing | Incorrect filter logic in Alpine | Check `filtered` computed property |
| Dark mode text not visible | Missing dark mode CSS | Verify `@media (prefers-color-scheme: dark)` blocks |
| Filter state lost on pagination | Query string not preserved | Check `filter.to_query_string()` includes all params |

---

## Performance Notes

✓ **No JavaScript build step** — All scripts inline/defer loaded
✓ **CSS-only mobile layout** — No separate HTMX endpoint
✓ **Local search** — Category filter doesn't hit server
✓ **Smooth AJAX** — HTMX handles all async loading
✓ **Lazy HTMX triggers** — Debounced search (delay:400ms)

**Estimated Load Times:**
- Category dropdown open: <10ms (Alpine)
- Search filter: <50ms (Array.filter)
- Page navigation: 100–500ms (HTMX + server)
- Mobile layout switch: 0ms (CSS media query)

---

## Browser Support

| Browser | Version | Support |
|---------|---------|---------|
| Chrome | 90+ | ✓ Full |
| Firefox | 88+ | ✓ Full |
| Safari | 14+ | ✓ Full |
| Edge | 90+ | ✓ Full |
| IE 11 | — | ✗ Not supported |

**Required Features:**
- CSS Grid
- CSS Media Queries
- ES6 (Alpine.js minimum)
- Fetch API (HTMX)

---

## File Locations

```
src/abn_combined/web/
├── templates/
│   ├── base.html                     ← Update with phase3 assets
│   ├── transactions.html             ← Replace with Phase 3 version
│   ├── _transactions_row.html        ← Keep (unchanged)
│   ├── _transactions_table.html      ← Replace with _transactions_table_phase3.html
│   └── _transactions_table_phase3.html (NEW)
├── static/
│   ├── phase1.css                    ← Keep
│   ├── app.css                       ← Keep
│   ├── phase3.css                    (NEW)
│   ├── vendor/
│   │   ├── bootstrap.min.css         ← Required
│   │   ├── alpine.min.js             ← Required
│   │   └── htmx.min.js               ← Required
│   └── js/
│       ├── transactions.js           ← Keep
│       └── phase3.js                 (NEW)

docs/phase/
├── phase2-transactions.html          ← Reference
├── phase3-transactions.html          ← Reference
├── _transactions_table_phase3.html   ← Reference copy
├── PHASE3_IMPLEMENTATION_NOTES.md    ← Full technical docs
├── PHASE3_INTEGRATION_GUIDE.md       ← Step-by-step guide
└── PHASE3_SUMMARY.md                 ← This file
```

---

## Next Steps

1. **Review Documentation:**
   - Read `PHASE3_IMPLEMENTATION_NOTES.md` (detailed)
   - Read `PHASE3_INTEGRATION_GUIDE.md` (step-by-step)

2. **Add Assets:**
   - Copy `phase3.css` to `/static/`
   - Copy `phase3.js` to `/static/js/`
   - Copy `_transactions_table_phase3.html` to `/templates/`

3. **Update Templates:**
   - Update `base.html` to include phase3 assets
   - Update `transactions.html` with Phase 3 components

4. **Test:**
   - Unit tests for new components
   - Manual testing at each breakpoint
   - Dark mode verification

5. **Deploy:**
   - Use feature flag or gradual rollout
   - Monitor error logs
   - Gather user feedback

---

## Questions?

Refer to:
- **Implementation Details:** `PHASE3_IMPLEMENTATION_NOTES.md`
- **Integration Steps:** `PHASE3_INTEGRATION_GUIDE.md`
- **Bootstrap Docs:** https://getbootstrap.com/docs/5.3/
- **Alpine Docs:** https://alpinejs.dev/
- **HTMX Docs:** https://htmx.org/

---

**Phase 3 Status:** ✓ Complete & Ready to Integrate
