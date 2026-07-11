# Phase 2 Quick Start: Copy-Paste Integration

This document provides ready-to-use code snippets for integrating Phase 2 into abn-combined.

---

## Step 1: Update `base.html`

Replace the `<head>` section:

```html
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}abn-combined{% endblock %}</title>
  
  <!-- Bootstrap 5.3 CSS -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <!-- Bootstrap Icons -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
  
  <!-- App Styles -->
  <link rel="stylesheet" href="/static/app.css">
  <link rel="stylesheet" href="/static/phase2.css">
</head>
<body>
  <header class="container-fluid bg-light border-bottom mb-3">
    <nav class="navbar navbar-expand-lg navbar-light">
      <div class="container">
        <a class="navbar-brand fw-bold" href="/">abn-combined</a>
        <div class="collapse navbar-collapse">
          <ul class="navbar-nav ms-auto">
            {% for path, label in nav_tabs %}
            <li class="nav-item">
              <a class="nav-link {% if path == active_path %}active{% endif %}" 
                 href="{{ path }}">{{ label }}</a>
            </li>
            {% endfor %}
          </ul>
        </div>
      </div>
    </nav>
  </header>
  
  <main class="container-fluid">
    {% block content %}{% endblock %}
  </main>

  <!-- HTMX -->
  <script src="/static/vendor/htmx.min.js" defer></script>
  <!-- Alpine.js -->
  <script src="/static/vendor/alpine.min.js" defer></script>
  <!-- Bootstrap 5.3 Bundle (includes Popper.js) -->
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" defer></script>
  
  <!-- App JS -->
  <script src="/static/js/transactions.js" defer></script>
  <script src="/static/js/phase2.js" defer></script>
</body>
</html>
```

---

## Step 2: Update `transactions.html`

Replace the entire `<form>` block (lines 12–112) with:

```html
{% extends "base.html" %}
{% block title %}Transactions — abn-combined{% endblock %}
{% block content %}

<hgroup class="mb-4">
  <h1>Transactions</h1>
  <p class="text-muted">Filter, sort and categorize. The full filter state lives in the URL — bookmark or share any view.</p>
</hgroup>

{# ===== FILTER BAR (Phase 1 + Phase 2) ===== #}
<form id="filter-bar" class="mb-3"
      hx-get="/transactions/table"
      hx-target="#txn-table"
      hx-swap="innerHTML"
      hx-push-url="true"
      hx-indicator="#txn-loading"
      hx-trigger="submit, change from:select, change from:input[type=date], change from:input[name=account], change from:input[type=checkbox]"
      x-data="txnFilterBar()">

  {# ===== Filter Row 1: Search + Presets + Sort + Filters Button ===== #}
  <div class="row g-2 mb-2 align-items-end">
    <div class="col-12 col-md-6" style="min-width: 16rem;">
      <label for="search-input" class="form-label">Search</label>
      <input id="search-input" type="search" name="q" class="form-control"
             placeholder="Search description or counterparty…"
             value="{{ filter.q or '' }}"
             hx-trigger="keyup changed delay:400ms, search">
    </div>

    <div class="col-6 col-md-2">
      <label for="preset-select" class="form-label">Date</label>
      <select id="preset-select" name="preset" class="form-select">
        <option value="">Any date</option>
        {% for p in presets %}
        <option value="{{ p }}" {% if filter.preset == p %}selected{% endif %}>{{ p.replace('-', ' ').title() }}</option>
        {% endfor %}
      </select>
    </div>

    <div class="col-6 col-md-2">
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

    <div class="col-12 col-md-2">
      <button type="button" class="btn btn-outline-primary w-100 position-relative"
              data-bs-toggle="offcanvas" data-bs-target="#advancedFiltersOffcanvas">
        Filters
        <span class="badge bg-danger position-absolute top-0 start-100 translate-middle"
              x-show="activeFilterCount > 0"
              x-text="activeFilterCount"
              style="display: none !important;">
        </span>
      </button>
    </div>
  </div>

  {# ===== Hidden Advanced Inputs (controlled by offcanvas) ===== #}
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

{# ===== OFFCANVAS ADVANCED FILTERS PANEL ===== #}
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

    {# Account #}
    <div class="mb-3">
      <label for="account-select" class="form-label">Account</label>
      <select id="account-select" name="account" class="form-select" form="filter-bar">
        <option value="">All accounts</option>
        {% for a in accounts %}
        <option value="{{ a }}" {% if a in filter.accounts %}selected{% endif %}>{{ a }}</option>
        {% endfor %}
      </select>
    </div>

    {# Categories #}
    <div class="mb-3">
      <label for="categories-select" class="form-label">Categories</label>
      <select id="categories-select" name="category" class="form-select" form="filter-bar" multiple>
        <option value="uncategorized" {% if 'uncategorized' in filter.categories %}selected{% endif %}>Uncategorized</option>
        {% for c in categories %}
        <option value="{{ c }}" {% if c in filter.categories %}selected{% endif %}>{{ c }}</option>
        {% endfor %}
      </select>
      <small class="form-text text-muted">Ctrl+Click to select multiple.</small>
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

<p id="txn-loading" class="htmx-indicator" role="status" aria-live="polite">Loading…</p>

{# ===== ACTIVE FILTER PILLS STRIP ===== #}
<div class="active-filters-strip" x-show="activeFilters.length > 0" style="display: none !important;">
  <div class="d-flex flex-wrap gap-2 align-items-center">
    <template x-for="filter in activeFilters" :key="filter.key">
      <span class="badge rounded-pill text-bg-primary d-flex align-items-center gap-2">
        <span x-text="`${filter.label}: ${filter.value}`"></span>
        <button type="button" class="btn btn-close btn-close-white" style="padding: 0;"
                @click="removeFilter(filter.key)" :aria-label="`Remove ${filter.label}`">
        </button>
      </span>
    </template>
    <button type="button" class="btn btn-sm btn-outline-secondary" @click="clearFilters()">
      Clear all
    </button>
  </div>
</div>

{# ===== TRANSACTIONS TABLE ===== #}
<div id="txn-table">
  {% include "_transactions_table.html" %}
</div>

{% endblock %}
```

---

## Step 3: Update `_transactions_table.html`

Add this at the very top of the file (before the existing chips section):

```html
{# Empty state card #}
{% if not page.total and chips %}
<div class="empty-state">
  <div class="empty-state-icon">
    <i class="bi bi-inbox"></i>
  </div>
  <h2 class="empty-state-heading">No transactions match your filters</h2>
  <div class="empty-state-subtext">
    {% if chips %}
    <p>You're filtering by:</p>
    <div class="empty-state-filters">
      <ul>
        {% for chip in chips %}
        <li>{{ chip.label }}</li>
        {% endfor %}
      </ul>
    </div>
    {% endif %}
    <p style="margin-top: 1rem;">Try adjusting your filters or clearing them entirely.</p>
  </div>
  <button type="button" class="btn btn-primary" @click="clearFilters()">
    Clear all filters
  </button>
</div>
{% endif %}

{# Keep the existing chips section here #}
{% if chips %}
<div class="chips">
  ...
</div>
{% endif %}
```

---

## Step 4: Copy Static Files

Copy these files to `/static/`:
- `phase2.css` → `/static/phase2.css`
- `phase2.js` → `/static/js/phase2.js`

---

## Step 5: Update `app.css`

You can keep the existing `.filter-bar`, `.chips` styles from Phase 1. Phase 2 styles are in `phase2.css` and don't conflict.

Optional: Remove Pico-specific styles if switching entirely to Bootstrap.

---

## Testing

```bash
source ~/venv/bin/activate
abn-combined --data-dir ./devdata
```

Then visit http://127.0.0.1:8000/transactions and:
1. Click "Filters" → offcanvas opens
2. Set a date range → click Apply → pills appear at top
3. Click × on a pill → pill removed, HTMX refetches
4. Click "Clear all" → all filters cleared

---

## Troubleshooting

### Offcanvas doesn't open
- Ensure Bootstrap Bundle JS is loaded: `<script src="bootstrap.bundle.min.js">`
- Check browser console for errors

### Pills don't appear
- Ensure `phase2.js` is loaded
- Check that `activeFilters` is being populated: open DevTools > Alpine tab

### Empty state doesn't show
- Ensure the `_transactions_table.html` includes the empty state markup
- Check that `not page.total and chips` is true in the template context

### HTMX not firing
- Ensure form has `hx-trigger` configured
- Check that form `id="filter-bar"` matches in all places
- Verify network tab shows GET requests to `/transactions/table`

---

## Done!

Your app now has Phase 2: Advanced filters, pills, badges, and empty states. All filter state remains in the URL. Enjoy!
