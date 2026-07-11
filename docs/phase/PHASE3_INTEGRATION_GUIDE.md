# Phase 3 Integration Guide

This guide explains how to integrate Phase 3 components into the existing abn-combined project.

---

## Step 1: Update `base.html` to Include Phase 3 Assets

**File:** `src/abn_combined/web/templates/base.html`

Add the new stylesheet and JavaScript to the `<head>` section:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}abn-combined{% endblock %}</title>

  <!-- Bootstrap 5.3 CSS -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmABheP7Wp1oDPDeKJ+/R5Have3f5FfO" crossorigin="anonymous">

  <!-- Bootstrap Icons -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">

  <!-- Custom theme and app styles -->
  <link rel="stylesheet" href="/static/phase1.css">
  <link rel="stylesheet" href="/static/app.css">
  <!-- NEW: Phase 3 styles -->
  <link rel="stylesheet" href="/static/phase3.css">

  <!-- Dependencies -->
  <script src="/static/vendor/htmx.min.js" defer></script>
  <script src="/static/vendor/alpine.min.js" defer></script>
  <!-- NEW: Phase 3 components -->
  <script src="/static/js/phase3.js" defer></script>
</head>
<body>
  <!-- ... rest of template unchanged ... -->
</body>
</html>
```

---

## Step 2: Update `transactions.html` to Use Phase 3 Components

**File:** `src/abn_combined/web/templates/transactions.html`

Replace the existing template with Phase 3-enhanced version. Key changes:

### A. Filter Bar Structure

Update the filter bar to use Bootstrap 5 grid and the new category picker:

```html
<form id="filter-bar" class="filter-bar mb-3"
      hx-get="/transactions/table"
      hx-target="#txn-table"
      hx-swap="innerHTML"
      hx-push-url="true"
      hx-indicator="#txn-loading"
      hx-trigger="submit, change from:select, change from:input[type=date], change from:input[name=account], change from:input[type=checkbox]"
      x-data="txnFilterBar()">

  {# Filter Row 1: Search + Date + Sort + Filters Button #}
  <div class="filter-row row g-2 align-items-end mb-2">
    <div class="col-auto flex-grow-1" style="min-width: 16rem;">
      <label for="search-input" class="form-label">Search</label>
      <input id="search-input" type="search" name="q" class="form-control"
             placeholder="Search description or counterparty…"
             value="{{ filter.q or '' }}"
             hx-get="/transactions/table" hx-target="#txn-table" hx-swap="innerHTML"
             hx-push-url="true" hx-indicator="#txn-loading"
             hx-trigger="keyup changed delay:400ms, search">
    </div>

    <div class="col-auto">
      <label for="preset-select" class="form-label">Date</label>
      <select id="preset-select" name="preset" class="form-select">
        <option value="">Any date</option>
        {% for p in presets %}
        <option value="{{ p }}" {% if filter.preset == p %}selected{% endif %}>{{ p.replace('-', ' ').title() }}</option>
        {% endfor %}
      </select>
    </div>

    <div class="col-auto">
      <label for="sort-select" class="form-label">Sort</label>
      <select id="sort-select" name="sort" class="form-select">
        <option value="date_desc" {% if filter.sort == 'date_desc' %}selected{% endif %}>Newest</option>
        <option value="date_asc" {% if filter.sort == 'date_asc' %}selected{% endif %}>Oldest</option>
        <option value="amount_desc" {% if filter.sort == 'amount_desc' %}selected{% endif %}>Amount ↓</option>
        <option value="amount_asc" {% if filter.sort == 'amount_asc' %}selected{% endif %}>Amount ↑</option>
        <option value="category_asc" {% if filter.sort == 'category_asc' %}selected{% endif %}>Category A→Z</option>
        <option value="category_desc" {% if filter.sort == 'category_desc' %}selected{% endif %}>Category Z→A</option>
      </select>
    </div>

    <div class="col-auto">
      <button type="button" class="btn btn-outline-primary position-relative"
              data-bs-toggle="offcanvas" data-bs-target="#advancedFiltersOffcanvas">
        Filters
        <span class="badge bg-danger position-absolute top-0 start-100 translate-middle"
              x-show="activeFilterCount > 0"
              x-text="activeFilterCount"
              style="display: none !important;"></span>
      </button>
    </div>
  </div>

  {# Hidden filter inputs (Phase 2) #}
  <div style="display: none;">
    <input type="date" name="date_from" value="{{ filter.date_from.isoformat() if filter.date_from else '' }}">
    <input type="date" name="date_to" value="{{ filter.date_to.isoformat() if filter.date_to else '' }}">
    <input type="number" step="0.01" name="amount_min" value="{{ filter.amount_min if filter.amount_min is not none else '' }}">
    <input type="number" step="0.01" name="amount_max" value="{{ filter.amount_max if filter.amount_max is not none else '' }}">
    <select name="account">
      <option value="">All accounts</option>
      {% for a in accounts %}
      <option value="{{ a }}" {% if a in filter.accounts %}selected{% endif %}>{{ a }}</option>
      {% endfor %}
    </select>
    {% for c in categories %}
    <input type="checkbox" name="category" value="{{ c }}" {% if c in filter.categories %}checked{% endif %}>
    {% endfor %}
    <input type="checkbox" name="category" value="uncategorized" {% if 'uncategorized' in filter.categories %}checked{% endif %}>
    {% for c in categories %}
    <input type="checkbox" name="exclude_category" value="{{ c }}" {% if c in filter.exclude_categories %}checked{% endif %}>
    {% endfor %}
    <input type="checkbox" name="exclude_category" value="uncategorized" {% if 'uncategorized' in filter.exclude_categories %}checked{% endif %}>
    {% for t in tags %}
    <input type="checkbox" name="tag" value="{{ t }}" {% if t in filter.tags %}checked{% endif %}>
    {% endfor %}
  </div>
</form>
```

### B. Offcanvas Panel (Updated with Category Picker)

Replace the categories select with the new checkbox-dropdown component:

```html
<div class="offcanvas offcanvas-end" tabindex="-1" id="advancedFiltersOffcanvas" aria-labelledby="advancedFiltersLabel">
  <div class="offcanvas-header">
    <h5 class="offcanvas-title" id="advancedFiltersLabel">Filters</h5>
    <button type="button" class="btn-close" data-bs-dismiss="offcanvas" aria-label="Close"></button>
  </div>

  <div class="offcanvas-body">
    {# Date Range #}
    <div class="mb-3">
      <label class="form-label">Date Range</label>
      <div class="input-group">
        <input type="date" class="form-control" name="date_from" form="filter-bar"
               value="{{ filter.date_from.isoformat() if filter.date_from else '' }}">
        <span class="input-group-text">–</span>
        <input type="date" class="form-control" name="date_to" form="filter-bar"
               value="{{ filter.date_to.isoformat() if filter.date_to else '' }}">
      </div>
    </div>

    {# Amount Range #}
    <div class="mb-3">
      <label class="form-label">Amount Range (€)</label>
      <div class="input-group">
        <span class="input-group-text">€</span>
        <input type="number" step="0.01" class="form-control" name="amount_min" form="filter-bar"
               placeholder="Min" value="{{ filter.amount_min if filter.amount_min is not none else '' }}">
        <span class="input-group-text">–</span>
        <span class="input-group-text">€</span>
        <input type="number" step="0.01" class="form-control" name="amount_max" form="filter-bar"
               placeholder="Max" value="{{ filter.amount_max if filter.amount_max is not none else '' }}">
      </div>
    </div>

    {# Account Select #}
    <div class="mb-3">
      <label for="account-select" class="form-label">Account</label>
      <select id="account-select" name="account" class="form-select" form="filter-bar">
        <option value="">All accounts</option>
        {% for a in accounts %}
        <option value="{{ a }}" {% if a in filter.accounts %}selected{% endif %}>{{ a }}</option>
        {% endfor %}
      </select>
    </div>

    {# PHASE 3: NEW Category Checkbox-Dropdown #}
    <div class="mb-3">
      <label class="form-label">Categories</label>
      <div class="dropdown" x-data="categoryPicker({{ categories | tojson }}, {{ filter.categories | tojson }})">
        <button class="btn btn-outline-secondary btn-sm dropdown-toggle w-100"
                type="button" id="categoryDropdownBtn"
                data-bs-toggle="dropdown" data-bs-auto-close="outside"
                x-text="buttonText()">
          Categories
        </button>
        <div class="dropdown-menu w-100" aria-labelledby="categoryDropdownBtn">
          {# Search input #}
          <div class="px-2 py-2">
            <input type="search" class="form-control form-control-sm"
                   placeholder="Search categories…"
                   x-model="searchQuery">
          </div>

          {# Checkbox list #}
          <div class="category-list">
            {# Uncategorized #}
            <div class="dropdown-item d-flex align-items-center gap-2">
              <input type="checkbox" class="form-check-input" id="cat-uncategorized"
                     name="category" value="uncategorized" form="filter-bar"
                     x-model="selected"
                     @change="updateHiddenInputs()">
              <label for="cat-uncategorized" class="form-check-label mb-0 flex-grow-1">
                Uncategorized
              </label>
            </div>

            {# Regular categories #}
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

            {# Empty state #}
            <div x-show="filtered.length === 0 && searchQuery.trim().length > 0"
                 class="dropdown-item disabled text-muted">
              No categories match your search.
            </div>
          </div>
        </div>
      </div>
      <small class="form-text text-muted">Type to filter categories</small>
    </div>

    {# Exclude Categories #}
    <div class="mb-3">
      <label for="exclude-categories-select" class="form-label">Exclude Categories</label>
      <select id="exclude-categories-select" name="exclude_category" class="form-select" form="filter-bar" multiple>
        <option value="uncategorized" {% if 'uncategorized' in filter.exclude_categories %}selected{% endif %}>Uncategorized</option>
        {% for c in categories %}
        <option value="{{ c }}" {% if c in filter.exclude_categories %}selected{% endif %}>{{ c }}</option>
        {% endfor %}
      </select>
      <small class="form-text text-muted">Ctrl+Click to select multiple.</small>
    </div>

    {# Tags #}
    <div class="mb-3">
      <label for="tags-select" class="form-label">Tags</label>
      <select id="tags-select" name="tag" class="form-select" form="filter-bar" multiple>
        {% for t in tags %}
        <option value="{{ t }}" {% if t in filter.tags %}checked{% endif %}>{{ t }}</option>
        {% else %}
        <option disabled>No tags yet.</option>
        {% endfor %}
      </select>
      <small class="form-text text-muted">Ctrl+Click to select multiple.</small>
    </div>
  </div>

  {# Offcanvas Footer #}
  <div class="offcanvas-footer border-top p-3 d-flex gap-2">
    <button type="button" class="btn btn-secondary flex-grow-1" @click="clearFilters()">
      Reset
    </button>
    <button type="button" class="btn btn-primary flex-grow-1" data-bs-dismiss="offcanvas" @click="submitForm()">
      Apply
    </button>
  </div>
</div>
```

### C. Active Filters Strip (Phase 2)

Keep the existing pills strip:

```html
<div class="active-filters-strip mb-3"
     x-show="activeFilters.length > 0"
     style="display: none !important;">
  <div class="d-flex flex-wrap gap-2 align-items-center">
    <template x-for="filter in activeFilters" :key="filter.key">
      <span class="badge rounded-pill text-bg-primary d-flex align-items-center gap-2">
        <span x-text="`${filter.label}: ${filter.value}`"></span>
        <button type="button" class="btn btn-close btn-close-white" style="padding: 0;"
                @click="removeFilter(filter.key)">
        </button>
      </span>
    </template>
    <button type="button" class="btn btn-sm btn-outline-secondary" @click="clearFilters()">
      Clear all
    </button>
  </div>
</div>
```

### D. Table Partial

Update the table include to use the new Phase 3 partial:

```html
<p id="txn-loading" class="htmx-indicator" role="status" aria-live="polite">Loading…</p>

<div id="txn-table">
  {% include "_transactions_table_phase3.html" %}
</div>
```

---

## Step 3: Create `_transactions_table_phase3.html` Partial

**File:** `src/abn_combined/web/templates/_transactions_table_phase3.html`

Copy the content from `docs/phase/_transactions_table_phase3.html` to the main templates directory.

---

## Step 4: Backend Requirements

Your FastAPI endpoint `/transactions/table` must return the following context variables:

### Existing Variables (Phases 1–2)

```python
{
    'filter': FilterState,          # Current filter state
    'chips': [ChipData],            # Active filter chips
    'page': PageInfo,               # Pagination info
    'rows': [TransactionRow],       # Current page transactions
    'categories': [str],            # All available categories
    'accounts': [str],              # All available accounts
    'tags': [str],                  # All available tags
    'presets': [str],               # Date presets
}
```

### New Variables (Phase 3)

None — Phase 3 uses existing page/filter variables. Just ensure `PageInfo` contains:

```python
class PageInfo:
    page: int                       # Current page (1-indexed)
    pages: int                      # Total page count
    total: int                      # Total row count
    has_prev: bool
    has_next: bool
    start_index: int                # For "Showing 1–20 of 214"
    end_index: int
```

### Alpine Template Functions (Required)

Add these methods to your Jinja2 environment or filter them in Python:

1. `filter.with_page(n)` — Return a new FilterState with page set to n
2. `filter.to_query_string()` — Serialize FilterState as query string

Example in Python:

```python
class FilterState:
    def with_page(self, page_num: int) -> 'FilterState':
        """Return copy with page number set."""
        f = copy(self)
        f.page = page_num
        return f

    def to_query_string(self) -> str:
        """Serialize to URL query string."""
        params = []
        if self.q:
            params.append(f'q={urllib.parse.quote(self.q)}')
        if self.preset:
            params.append(f'preset={self.preset}')
        if self.sort:
            params.append(f'sort={self.sort}')
        # ... add all other filters ...
        if self.page > 1:
            params.append(f'page={self.page}')
        return '&'.join(params)
```

---

## Step 5: Test the Integration

### Unit Tests

```python
def test_category_picker_renders():
    """Ensure category picker Alpine component loads."""
    response = client.get('/transactions')
    assert 'categoryPicker' in response.text
    assert 'dropdown-toggle' in response.text

def test_pagination_renders():
    """Ensure pagination component renders for multi-page results."""
    response = client.get('/transactions/table?page=1')
    assert 'pagination' in response.text
    assert 'Page 1 of' in response.text

def test_mobile_card_layout():
    """Ensure mobile card structure is present."""
    response = client.get('/transactions')
    assert 'txn-card' in response.text
    assert 'txn-card-header' in response.text
```

### Manual Testing

1. **Desktop (≥1024px):**
   - Filter bar renders horizontally
   - Table displays normally
   - Offcanvas opens when "Filters" clicked
   - Category dropdown opens with search

2. **Tablet (768–1024px):**
   - Offcanvas filters use two-column layout
   - Table still displays

3. **Mobile (<768px):**
   - Table hidden, cards visible
   - Cards stack vertically
   - Offcanvas buttons full-width
   - Cards expandable for detail

### Browser DevTools

1. Open DevTools → Responsive Design Mode
2. Test at each breakpoint:
   - iPhone SE (375px)
   - iPhone 12 Pro (390px)
   - iPad (768px)
   - Desktop (1024px+)

---

## Step 6: Rollout Strategy

### Option A: Gradual Migration

1. Keep existing `transactions.html` (Phase 2)
2. Create new `transactions_phase3.html`
3. Use feature flag to switch routes:
   ```python
   @app.get("/transactions")
   def transactions(use_phase3: bool = False):
       template = "transactions_phase3.html" if use_phase3 else "transactions.html"
       return templates.TemplateResponse(template, context)
   ```

4. Test Phase 3 with internal users
5. Migrate to Phase 3 by default
6. Remove Phase 2 template after 2-week stability period

### Option B: Immediate Rollout

1. Update `transactions.html` directly to Phase 3
2. Run full test suite
3. Monitor error logs for 24 hours
4. Rollback plan: revert template to Phase 2

---

## Troubleshooting

### Issue: Category picker not opening

**Solution:**
- Verify `data-bs-toggle="dropdown"` is present
- Check that Bootstrap JS is loaded (`bootstrap.bundle.min.js`)
- Ensure `data-bs-auto-close="outside"` prevents premature close

### Issue: Pagination links not working

**Solution:**
- Verify HTMX is loaded (`htmx.min.js`)
- Check that `hx-get`, `hx-target`, `hx-swap` attributes are present
- Verify server endpoint `/transactions/table` exists and returns partial HTML

### Issue: Mobile cards not showing

**Solution:**
- Verify `phase3.css` is loaded
- Check browser DevTools for CSS media query (@media max-width: 767.98px)
- Resize browser window to test responsiveness

### Issue: Filter state lost during pagination

**Solution:**
- Verify `filter.with_page(n).to_query_string()` includes all filter params
- Check URL bar shows query parameters after pagination
- Ensure hidden form inputs are synchronized with visible filters

---

## References

- [Bootstrap 5 Documentation](https://getbootstrap.com/docs/5.3/)
- [Alpine.js Documentation](https://alpinejs.dev/)
- [HTMX Documentation](https://htmx.org/)
- [abn-combined Architecture](../architecture.md)
- [Phase 3 Implementation Notes](./PHASE3_IMPLEMENTATION_NOTES.md)
