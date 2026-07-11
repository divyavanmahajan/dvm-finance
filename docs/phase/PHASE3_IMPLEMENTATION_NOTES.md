# Phase 3: Bootstrap 5 Redesign — Implementation Notes

## Overview

Phase 3 extends the Bootstrap 5 redesign (Phases 1–2) with three major enhancements:

1. **Category Checkbox-Dropdown** — Alpine-controlled searchable dropdown for category filtering
2. **Transaction Table Pagination** — Bootstrap pagination component wired to HTMX
3. **Mobile Table Layout** — Stacked cards on mobile (<md), table on desktop (md+)

All components use CSS media queries (no separate HTMX partial) and maintain the Golden Principle that filter state always lives in the URL query string.

---

## File Structure

```
src/abn_combined/web/
├── templates/
│   ├── transactions.html              (existing; needs update to include phase3 assets)
│   ├── _transactions_row.html          (existing; unchanged)
│   ├── _transactions_table.html        (existing; superseded by _transactions_table_phase3.html)
│   └── _transactions_table_phase3.html (NEW: desktop table + mobile cards + pagination)
├── static/
│   ├── phase3.css                      (NEW: Category dropdown, mobile cards, pagination)
│   ├── js/
│   │   ├── transactions.js             (existing; unchanged)
│   │   └── phase3.js                   (NEW: Alpine components + HTMX handlers)
│   └── phase1.css                      (existing; still needed for base styling)
└── ...

docs/phase/
├── phase2-transactions.html            (reference: Phase 2 template)
├── phase3-transactions.html            (NEW: Phase 3 reference template)
├── _transactions_table_phase3.html     (NEW: Table partial)
└── PHASE3_IMPLEMENTATION_NOTES.md      (this file)
```

---

## Component 1: Category Checkbox-Dropdown

### Design

- **Trigger:** Bootstrap `.btn btn-outline-secondary` with `.dropdown-toggle`
- **Behavior:** `data-bs-auto-close="outside"` keeps dropdown open during checkbox interaction
- **Search:** Filter categories in real-time via Alpine `x-model="searchQuery"`
- **Button Text:** Shows "N selected" or "All categories" depending on state
- **Form Sync:** Hidden checkboxes in main filter-bar form stay synchronized

### Implementation

**Template (phase3-transactions.html):**

```html
<div class="dropdown" x-data="categoryPicker({{ categories | tojson }}, {{ filter.categories | tojson }})">
  <button class="btn btn-outline-secondary btn-sm dropdown-toggle w-100"
          type="button" id="categoryDropdownBtn"
          data-bs-toggle="dropdown" data-bs-auto-close="outside"
          aria-expanded="false"
          x-text="buttonText()">
    Categories
  </button>
  <div class="dropdown-menu w-100" aria-labelledby="categoryDropdownBtn">
    <!-- Search input -->
    <div class="px-2 py-2">
      <input type="search" class="form-control form-control-sm"
             placeholder="Search categories…"
             x-model="searchQuery">
    </div>

    <!-- Checkbox list (filtered) -->
    <div class="category-list">
      <!-- "Uncategorized" checkbox -->
      <div class="dropdown-item d-flex align-items-center gap-2">
        <input type="checkbox" class="form-check-input" id="cat-uncategorized"
               name="category" value="uncategorized" form="filter-bar"
               x-model="selected"
               @change="updateHiddenInputs()">
        <label for="cat-uncategorized" class="form-check-label mb-0 flex-grow-1">
          Uncategorized
        </label>
      </div>

      <!-- Regular categories (x-for loop) -->
      <template x-for="cat in filtered" :key="cat">
        <div class="dropdown-item d-flex align-items-center gap-2">
          <input type="checkbox" class="form-check-input"
                 :id="'cat-' + slugify(cat)"
                 name="category" :value="cat" form="filter-bar"
                 x-model="selected"
                 @change="updateHiddenInputs()">
          <label :for="'cat-' + slugify(cat)" class="form-check-label mb-0 flex-grow-1">
            <span x-text="cat"></span>
          </label>
        </div>
      </template>
    </div>
  </div>
</div>
```

**Alpine Component (js/phase3.js):**

```javascript
window.Alpine.data('categoryPicker', (allCategories, initialSelected) => ({
  selected: initialSelected || [],
  searchQuery: '',
  allCats: allCategories,

  get filtered() {
    if (!this.searchQuery.trim()) {
      return this.allCats;
    }
    const q = this.searchQuery.toLowerCase();
    return this.allCats.filter(cat => cat.toLowerCase().includes(q));
  },

  buttonText() {
    if (this.selected.length === 0) {
      return 'Categories';
    }
    if (this.selected.length === this.allCats.length + 1) {
      return 'All categories';
    }
    return `${this.selected.length} selected`;
  },

  updateHiddenInputs() {
    const categoryInputs = document.querySelectorAll('input[name="category"][form="filter-bar"]');
    categoryInputs.forEach(input => {
      input.checked = this.selected.includes(input.value);
    });
    // Trigger HTMX form submission
    htmx.trigger(document.getElementById('filter-bar'), 'change');
  },

  slugify(text) {
    return text.toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]/g, '');
  },
}))
```

### Form Integration

1. **Hidden Inputs:** The main filter-bar form contains hidden category checkboxes (in the `<div style="display: none;">` block).
2. **Sync Path:** When user selects/deselects in dropdown → Alpine updates `selected` array → `updateHiddenInputs()` sets hidden checkbox states → HTMX trigger fires → server re-filters and returns new table.
3. **URL State:** The filter-bar form includes `hx-include="*"` (implicit via form=filter-bar) so all checkbox states are captured in the query string when HTMX submits.

### CSS

**phase3.css** provides:
- `.category-list`: scrollable container with max-height
- `.dropdown-item.d-flex`: checkbox + label layout with hover state
- `.form-check-input`, `.form-check-label`: Bootstrap checkbox styling
- Dark mode support via `@media (prefers-color-scheme: dark)`

---

## Component 2: Transaction Table Pagination

### Design

- **Component:** Bootstrap `.pagination .pagination-sm`
- **Buttons:** Previous / numbered pages / Next (disabled when at boundary)
- **Smart Ellipsis:** Shows "1 … 3 4 5 … 10" if there are gaps
- **Current Page:** Highlighted with `.active` state
- **HTMX Wiring:** Each page link includes `hx-get`, `hx-target="#txn-table"`, `hx-push-url`
- **Info Text:** "Page N of M" below pagination

### Implementation

**Template (_transactions_table_phase3.html):**

```html
{% if page.pages > 1 %}
<nav aria-label="Pagination" class="mt-4">
  <ul class="pagination pagination-sm justify-content-center">
    <!-- Previous button -->
    <li class="page-item {% if not page.has_prev %}disabled{% endif %}">
      {% if page.has_prev %}
      <a class="page-link" 
         hx-get="/transactions/table?{{ filter.with_page(page.page - 1).to_query_string() }}"
         hx-target="#txn-table" hx-swap="innerHTML"
         hx-push-url="/?{{ filter.with_page(page.page - 1).to_query_string() }}">
        Previous
      </a>
      {% else %}
      <span class="page-link disabled">Previous</span>
      {% endif %}
    </li>

    <!-- Page number loop (with smart ellipsis) -->
    {% set start_page = [1, page.page - 2] | max %}
    {% set end_page = [page.pages, page.page + 2] | min %}

    {% if start_page > 1 %}
      <li class="page-item">
        <a class="page-link" 
           hx-get="/transactions/table?{{ filter.with_page(1).to_query_string() }}"
           hx-target="#txn-table" hx-swap="innerHTML">
          1
        </a>
      </li>
      {% if start_page > 2 %}
      <li class="page-item disabled"><span class="page-link">…</span></li>
      {% endif %}
    {% endif %}

    <!-- Visible page numbers -->
    {% for p in range(start_page, end_page + 1) %}
    <li class="page-item {% if p == page.page %}active{% endif %}">
      {% if p == page.page %}
      <span class="page-link">{{ p }}</span>
      {% else %}
      <a class="page-link" 
         hx-get="/transactions/table?{{ filter.with_page(p).to_query_string() }}"
         hx-target="#txn-table" hx-swap="innerHTML"
         hx-push-url="/?{{ filter.with_page(p).to_query_string() }}">
        {{ p }}
      </a>
      {% endif %}
    </li>
    {% endfor %}

    <!-- Ellipsis + last page if needed -->
    {% if end_page < page.pages %}
      {% if end_page < page.pages - 1 %}
      <li class="page-item disabled"><span class="page-link">…</span></li>
      {% endif %}
      <li class="page-item">
        <a class="page-link" 
           hx-get="/transactions/table?{{ filter.with_page(page.pages).to_query_string() }}"
           hx-target="#txn-table" hx-swap="innerHTML">
          {{ page.pages }}
        </a>
      </li>
    {% endif %}

    <!-- Next button -->
    <li class="page-item {% if not page.has_next %}disabled{% endif %}">
      {% if page.has_next %}
      <a class="page-link" 
         hx-get="/transactions/table?{{ filter.with_page(page.page + 1).to_query_string() }}"
         hx-target="#txn-table" hx-swap="innerHTML"
         hx-push-url="/?{{ filter.with_page(page.page + 1).to_query_string() }}">
        Next
      </a>
      {% else %}
      <span class="page-link disabled">Next</span>
      {% endif %}
    </li>
  </ul>
</nav>

<!-- Page info text -->
<div class="text-center mt-2">
  <small class="text-muted">Page {{ page.page }} of {{ page.pages }}</small>
</div>
{% endif %}
```

### CSS

**phase3.css** provides:
- `.pagination`: flex container with center alignment
- `.page-link`: styled links with hover/active states
- `.page-link.disabled`: opacity and pointer-events disabled
- `.page-item.active .page-link`: highlighted current page
- Dark mode support

### Backend Requirements

The `/transactions/table` endpoint must accept and return:
- `page` (query param): current page number (1-indexed)
- `page_size` (query param): items per page (default 20)
- `page.total`: total row count
- `page.pages`: total page count
- `page.page`: current page number
- `page.has_prev`, `page.has_next`: boolean flags
- `page.start_index`, `page.end_index`: human-readable range ("1–20")
- `rows`: list of transaction rows for current page

---

## Component 3: Mobile Table Layout

### Design

**Desktop (md+ / 768px+):**
- Full table rendered (`.txn-table`)
- Mobile cards hidden (`.d-md-none`)

**Mobile (<md / <768px):**
- Table hidden (`.d-md-block`)
- Stacked cards rendered (`.txn-cards-container`)
- Cards use `.d-md-none` to show only on mobile

### Card Structure

Each card (`.txn-card`) contains:

```
┌─────────────────────────────────┐
│ 2026-07-08          −€ 43.17    │  ← Header (date + amount)
├─────────────────────────────────┤
│ Albert Heijn 1653 (bold)         │  ← Description
│ Category: Groceries              │
│ Account: NL91ABNA…              │
│ Tags: shopping, weekly           │  (if present)
│ Source: rule #42                 │
├─────────────────────────────────┤
│ [Show detail]  [+ rule]          │  ← Footer (buttons)
└─────────────────────────────────┘

Hidden detail (x-show="detailOpen"):
  Full Description: …
  Amount: −43.17 EUR
  Date: 2026-07-08
  …
```

### Implementation

**Template (_transactions_table_phase3.html):**

```html
<div class="d-md-none">
  <div class="txn-cards-container">
    {% for row in rows %}
      {% set t = row.txn %}
      <div class="txn-card" x-data="{ detailOpen: false }">
        <!-- Header -->
        <div class="txn-card-header">
          <div class="txn-card-date">{{ t.transactiondate.isoformat() }}</div>
          <div class="txn-card-amount {% if t.amount < 0 %}neg{% else %}pos{% endif %}">
            {{ '−€' if t.amount < 0 else '+€' }} {{ '%.2f'|format(t.amount | abs) }}
          </div>
        </div>

        <!-- Body -->
        <div class="txn-card-body">
          <!-- Description -->
          <div class="txn-card-row">
            <div class="txn-card-value" style="width: 100%;">
              <strong>{{ (t.description or '')[:80] }}</strong>
            </div>
          </div>

          <!-- Category -->
          <div class="txn-card-row">
            <div class="txn-card-label">Category:</div>
            <div class="txn-card-value">
              {% if row.effective_category %}
                <span class="badge">{{ row.effective_category }}</span>
              {% else %}
                <em>uncategorized</em>
              {% endif %}
              {% if row.is_manual %}<span class="badge manual">M</span>{% endif %}
            </div>
          </div>

          <!-- Account, Tags, Source... -->
          <!-- (see template for full structure) -->
        </div>

        <!-- Detail (expandable) -->
        <div class="txn-card-detail" x-show="detailOpen" x-cloak>
          <dl>
            <dt>Full Description:</dt>
            <dd>{{ t.description or '—' }}</dd>
            <!-- ... -->
          </dl>
        </div>

        <!-- Footer -->
        <div class="txn-card-footer">
          <button type="button" class="btn btn-sm btn-outline-secondary flex-grow-1"
                  @click="detailOpen = !detailOpen"
                  x-text="detailOpen ? 'Hide detail' : 'Show detail'">
            Show detail
          </button>
          <a href="/rules/new?from_transaction={{ t.id }}"
             class="btn btn-sm btn-outline-primary">
            + rule
          </a>
        </div>
      </div>
    {% endfor %}
  </div>
</div>
```

### CSS

**phase3.css** provides:

```css
/* Mobile (<md): Hide table, show cards */
@media (max-width: 767.98px) {
  .txn-table { display: none !important; }
  .txn-card { display: block; }
}

/* Desktop (md+): Show table, hide cards */
@media (min-width: 768px) {
  .txn-table { display: table; }
  .txn-card { display: none !important; }
}

.txn-card {
  background-color: #fff;
  border: 1px solid var(--bs-border-color);
  border-radius: 0.5rem;
  padding: 1rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.txn-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--bs-border-color);
}

.txn-card-amount {
  font-weight: 600;
  font-family: 'Monaco', 'Courier New', monospace;
}

.txn-card-amount.pos { color: var(--money-positive); }
.txn-card-amount.neg { color: var(--money-negative); }

.txn-card-body {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.txn-card-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.9rem;
}

.txn-card-label { font-weight: 500; color: #666; min-width: 6rem; }
.txn-card-value { text-align: right; color: #333; }

/* Dark mode */
@media (prefers-color-scheme: dark) {
  .txn-card {
    background-color: #252525;
    border-color: #444;
  }
  .txn-card-label { color: #aaa; }
  .txn-card-value { color: #e0e0e0; }
}
```

### Responsive Adjustments

**Extra small devices (<sm / <576px):**
- Card padding reduced to `0.75rem`
- Card header stacks vertically
- Amount aligns to right
- Font sizes slightly reduced
- Pagination links smaller

---

## Responsive Filter Panel

The offcanvas advanced filters panel stacks responsively:

### Layout Modes

**Mobile (<md):**
- Single column, full-width form controls

**Tablet (md+):**
- Two-column grid layout
- Date range + Amount range in column 1
- Account + Categories in column 2

**Desktop (xl+):**
- Four-column grid layout

**Extra Small (<sm):**
- Offcanvas footer buttons stack to full-width

### CSS Implementation

```css
@media (max-width: 575.98px) {
  .offcanvas-footer {
    flex-direction: column !important;
  }
  .offcanvas-footer .btn { width: 100%; }
}

@media (min-width: 768px) {
  .offcanvas-body {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
  }
}

@media (min-width: 1200px) {
  .offcanvas-body {
    grid-template-columns: 1fr 1fr 1fr 1fr;
  }
}
```

---

## Integration with Existing Phases

### Phase 1 (Navbar + Search + Sort)
- **Status:** Unchanged
- **Location:** `base.html` + `app.css`
- No modifications needed.

### Phase 2 (Filter Bar + Offcanvas + Pills)
- **Status:** Mostly unchanged
- **Enhancements:**
  - Category multi-select is now replaced with searchable checkbox-dropdown (Component 1)
  - Active filter pills strip extended to support category pills
  - Offcanvas layout now responsive (stacked on mobile, grid on desktop)
- **Hidden Inputs:** Still present; now wired to Alpine component via `form="filter-bar"` binding

### Phase 3 (Additions)
- Category checkbox-dropdown (Alpine + Bootstrap dropdown)
- Pagination with Bootstrap `.pagination`
- Mobile card layout (CSS media queries, no HTMX partial)

---

## HTMX Integration

### Flow Diagram

```
User interacts with category dropdown (select/deselect)
  ↓
Alpine `x-model="selected"` updates array
  ↓
`@change="updateHiddenInputs()"` fires
  ↓
Hidden checkboxes in filter-bar updated
  ↓
`htmx.trigger(filterForm, 'change')` fires HTMX
  ↓
GET /transactions/table?category=X&category=Y&...
  ↓
Server returns _transactions_table_phase3.html partial
  ↓
`hx-swap="innerHTML"` updates #txn-table
  ↓
`hx-push-url="true"` updates browser URL (Golden Principle 8)
  ↓
Alpine re-initializes for new content
```

### HTMX Event Handlers (phase3.js)

```javascript
// Reinitialize Alpine components after HTMX swap
document.addEventListener('htmx:afterSwap', function(evt) {
  if (evt.detail.target.id === 'txn-table') {
    Alpine.scan(evt.detail.target);
    scrollToElement('#txn-table');
  }
});

// Show loading indicator
document.addEventListener('htmx:xhr:progress', function(evt) {
  document.getElementById('txn-loading').style.display = 'block';
});

// Hide loading indicator after swap
document.addEventListener('htmx:afterSettle', function(evt) {
  document.getElementById('txn-loading').style.display = 'none';
});
```

---

## Testing Checklist

### Category Picker
- [ ] Dropdown opens/closes with mouse click
- [ ] Checkboxes toggle state on click
- [ ] Search query filters categories in real-time
- [ ] Button text updates ("N selected", "All categories", "Categories")
- [ ] Selecting all categories shows "All categories"
- [ ] Hidden filter-bar checkboxes stay synchronized
- [ ] Category selection triggers HTMX fetch and URL update
- [ ] Page refreshes with bookmarked URL re-loads category selections

### Pagination
- [ ] Previous/Next buttons disabled at boundaries
- [ ] Page numbers are clickable (except current page)
- [ ] Ellipsis appears for large page counts
- [ ] Current page is highlighted with `.active` style
- [ ] Clicking page number fetches new table and updates URL
- [ ] "Page N of M" text updates after navigation
- [ ] All filter state is preserved when paginating

### Mobile Layout
- [ ] **Desktop (≥768px):** Table renders, cards hidden
- [ ] **Mobile (<768px):** Cards render, table hidden
- [ ] **Card styling:** Amount color-coded (positive/negative)
- [ ] **Card detail:** Expand/collapse with button
- [ ] **Card actions:** "Show detail" and "+ rule" buttons visible and functional
- [ ] **Offcanvas filters:** Buttons stack full-width on mobile
- [ ] **Responsive text:** Font sizes and padding adjust on mobile

### Dark Mode
- [ ] Category dropdown renders correctly
- [ ] Card backgrounds and text colors adjust
- [ ] Pagination links visible with proper contrast
- [ ] All badges and badges visible

### Integration
- [ ] All filter types (search, date, amount, account, categories, tags) work together
- [ ] URL state always reflects current filters and pagination
- [ ] Bookmarked URLs restore full filter + pagination state
- [ ] "Clear all" resets all filters and returns to page 1
- [ ] Loading indicator shows during HTMX fetch

---

## Breakpoints Reference

Bootstrap 5 standard breakpoints used:

| Breakpoint | Min-width | Device          |
|------------|-----------|-----------------|
| xs         | —         | Mobile          |
| sm         | 576px     | Small mobile    |
| md         | 768px     | Tablet          |
| lg         | 992px     | Desktop         |
| xl         | 1200px    | Large desktop   |
| xxl        | 1400px    | Extra large     |

**Phase 3 uses:**
- `<md` (max-width: 767.98px): Mobile cards + stacked buttons
- `≥md` (min-width: 768px): Desktop table + inline buttons
- `≥xl` (min-width: 1200px): Four-column filter grid

---

## Performance Notes

1. **No Second HTMX Endpoint:** Mobile and desktop layouts use the same table partial, with CSS media queries switching display. This avoids code duplication and ensures state consistency.
2. **Pagination Links:** Direct HTMX integration (no JavaScript pagination logic) — simple, fast, maintains URL state.
3. **Category Search:** Local Alpine filtering (no server round-trip) — instant search with no latency.
4. **Loading Indicator:** HTMX manages visibility via event handlers — no polling or manual management.

---

## Future Enhancements

1. **Page Size Selector:** Add dropdown to change items per page (10, 25, 50, 100).
2. **Sort Preservation:** When paginating, preserve current sort order (already supported via `filter.to_query_string()`).
3. **Keyboard Navigation:** Support arrow keys in category dropdown for accessibility.
4. **Inline Category Editing:** Allow category change from card without opening detail row.
5. **Swipe Gestures:** Mobile card swipe to expand/collapse detail (optional enhancement).

---

## References

- **Bootstrap 5 Pagination:** https://getbootstrap.com/docs/5.3/components/pagination/
- **Bootstrap 5 Dropdowns:** https://getbootstrap.com/docs/5.3/components/dropdowns/
- **Alpine.js:** https://alpinejs.dev/
- **HTMX:** https://htmx.org/
- **Project Golden Principles:** See `docs/core-beliefs.md`

---

## Deployment Notes

1. **Assets to Include:**
   - `/static/phase3.css` (new)
   - `/static/js/phase3.js` (new)
   - Update `base.html` to load these assets

2. **Backward Compatibility:**
   - Phase 1–2 CSS/JS remains unchanged
   - Existing templates (phase1-transactions.html, phase2-transactions.html) can coexist
   - Gradual migration: update `/transactions` route to use phase3-transactions.html

3. **A/B Testing:**
   - Keep Phase 2 template active during transition
   - Use feature flag or URL param to switch between versions
   - Once stable, retire Phase 2 template and associated CSS

---

**Phase 3 Status:** ✓ Design Complete | ✓ Template Ready | ✓ CSS Ready | ✓ JS Components Ready
