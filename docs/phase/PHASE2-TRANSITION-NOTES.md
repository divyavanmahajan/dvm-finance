# Phase 2 Transition Notes: Pico → Bootstrap

This document explains how Phase 2 components fit into the existing abn-combined architecture and how to transition from Pico CSS to Bootstrap 5.

---

## Current State (Phase 1)

**Framework:** Pico CSS v2
- Minimal, classless framework
- Semantic HTML with few utility classes
- Lightweight (12KB minified)
- No JavaScript required

**Current Styles:**
- Filter bar: `.filter-row`, `.filter-bar`, `.multi`, `.multi-menu` (custom)
- Chips: `.chips`, `.chip`, `.chip-clear` (custom)
- Table: `.txn-table`, `.badge` (custom), `.pagination` (custom)
- Form controls: semantic `<label>`, `<input>`, `<select>`, `<button>`

**Filter Interactivity:**
- Alpine.js for disclosure (`advanced` toggle, multi-select dropdowns)
- HTMX for form submission and URL state
- All state in URL query params (Golden Principle 8)

---

## Phase 2 Design (Bootstrap 5.3)

**Framework:** Bootstrap 5.3
- Comprehensive component library
- Utility-first classes (`.btn`, `.form-control`, `.row`, `.col-*`)
- Powerful JavaScript components (offcanvas, modals, dropdowns)
- Larger bundle but more features (83KB CSS + 30KB JS)

**New Components:**
- `.offcanvas.offcanvas-end` — slide-in filter panel
- `.badge.rounded-pill` — filter pills
- `.empty-state` (custom) — empty state card
- `.position-absolute.top-0.start-100` — badge positioning

**Why Bootstrap over Pico?**
1. **Offcanvas:** Built-in, no custom JS needed (vs. DIY modal)
2. **Responsiveness:** Grid system for multi-column layouts
3. **Component library:** Buttons, badges, forms already styled
4. **Icons:** Bootstrap Icons for visual richness
5. **Accessibility:** WCAG AA by default

---

## Migration Strategy

### Option A: Full Bootstrap (Recommended)
1. Replace Pico CDN with Bootstrap 5.3 + Icons
2. Update `base.html` structure (flex nav instead of Pico's semantic nav)
3. Convert existing Pico classes to Bootstrap classes:
   - Pico `<button>` → Bootstrap `.btn.btn-primary` (or `.btn.btn-outline-*`)
   - Pico `<input>` → Bootstrap `.form-control`
   - Pico `<select>` → Bootstrap `.form-select`
   - Pico tables → Bootstrap `.table.table-striped`
4. Test all pages (Transactions, Rules, Tags, Budgets, Trends, etc.)
5. Remove `pico.min.css` from vendor

**Effort:** 2–4 hours (refactor existing templates)
**Benefit:** Consistent design system, easier maintenance

### Option B: Pico + Bootstrap Hybrid
1. Keep Pico CSS for base styling
2. Add Bootstrap 5.3 CSS (after Pico in cascade)
3. Use Bootstrap classes only for Phase 2 components
4. Phase 1 stays Pico-styled, Phase 2 uses Bootstrap

**Effort:** 1 hour (add CDN link, copy Phase 2 files)
**Benefit:** Minimal disruption, Phase 2 ready to ship

**Downside:** CSS conflicts (both define `.btn`, `.badge`, etc.)

### Option C: Selective Pico Removal
1. Keep Phase 1 as-is (Pico)
2. Isolate Phase 2 in a Bootstrap wrapper div
3. Style Phase 2 with Bootstrap, Phase 1 with Pico
4. Scoped CSS to avoid conflicts

**Effort:** 3 hours (CSS scoping + careful testing)
**Benefit:** Zero risk to Phase 1

---

## Recommended: Option A (Full Bootstrap)

Here's why and how:

### CSS Cascade Strategy
```html
<!-- base.html -->
<link href="bootstrap.min.css" rel="stylesheet">  <!-- Bootstrap base -->
<link rel="stylesheet" href="/static/app.css">     <!-- App-specific overrides -->
<link rel="stylesheet" href="/static/phase2.css">  <!-- Phase 2 additions -->
```

### Conflicts to Watch For

| Pico Element | Bootstrap Class | Resolution |
|--------------|-----------------|-----------|
| `<button>` | `.btn` + color class | Update templates to add classes |
| `<input>` | `.form-control` | Add to inputs |
| `<select>` | `.form-select` | Add to selects |
| `.badge` | `.badge` (both exist) | Merge custom badge styles into Bootstrap |
| `<table>` | `.table` | Add to tables |
| `<nav>` | `.navbar` | Restructure navbar |

### Step-by-Step Conversion

#### 1. Update base.html
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}abn-combined{% endblock %}</title>
  
  <!-- Bootstrap 5.3 -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
  
  <!-- App CSS (Pico removed) -->
  <link rel="stylesheet" href="/static/app.css">
  <link rel="stylesheet" href="/static/phase2.css">
</head>
<body>
  <!-- Navbar (Bootstrap) -->
  <header class="navbar navbar-expand-lg navbar-light bg-light border-bottom">
    <div class="container-fluid">
      <a class="navbar-brand fw-bold" href="/">abn-combined</a>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="navbarNav">
        <ul class="navbar-nav ms-auto">
          {% for path, label in nav_tabs %}
          <li class="nav-item">
            <a class="nav-link {% if path == active_path %}active{% endif %}" href="{{ path }}">{{ label }}</a>
          </li>
          {% endfor %}
        </ul>
      </div>
    </div>
  </header>

  <main class="container-fluid">
    {% block content %}{% endblock %}
  </main>

  <!-- Scripts -->
  <script src="/static/vendor/htmx.min.js" defer></script>
  <script src="/static/vendor/alpine.min.js" defer></script>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" defer></script>
  <script src="/static/js/transactions.js" defer></script>
  <script src="/static/js/phase2.js" defer></script>
</body>
</html>
```

#### 2. Update Button Styles
```html
<!-- Pico (before) -->
<button type="button" class="secondary outline">More filters</button>
<a role="button" class="secondary">Reset</a>

<!-- Bootstrap (after) -->
<button type="button" class="btn btn-outline-secondary">More filters</button>
<a role="button" class="btn btn-outline-secondary">Reset</a>
```

#### 3. Update Form Controls
```html
<!-- Pico (before) -->
<label>Search <input type="search" name="q" placeholder="..."></label>
<label>Date <select name="preset">...</select></label>

<!-- Bootstrap (after) -->
<label for="search" class="form-label">Search</label>
<input id="search" type="search" name="q" class="form-control" placeholder="...">
<label for="preset" class="form-label">Date</label>
<select id="preset" name="preset" class="form-select">...</select>
```

#### 4. Update Tables
```html
<!-- Pico (before) -->
<table>
  <thead>...</thead>
  <tbody>...</tbody>
</table>

<!-- Bootstrap (after) -->
<table class="table table-striped table-hover">
  <thead>...</thead>
  <tbody>...</tbody>
</table>
```

#### 5. Update Chips/Badges
```html
<!-- Pico chip (before) -->
<a class="chip" href="...">Amount: €50–€200 <span>✕</span></a>

<!-- Bootstrap badge (after, Phase 1) -->
<span class="badge rounded-pill text-bg-primary">Amount: €50–€200</span>

<!-- Or Bootstrap badge + button (Phase 2) -->
<span class="badge rounded-pill text-bg-primary d-flex align-items-center gap-2">
  Amount: €50–€200
  <button type="button" class="btn-close btn-close-white" style="padding: 0;"></button>
</span>
```

---

## Testing Plan

After converting to Bootstrap:

1. **Visual regression:** Screenshot each page, compare to before
2. **Responsive:** Test on mobile (320px), tablet (768px), desktop (1024px+)
3. **Functionality:**
   - Filter bar works (HTMX, Alpine)
   - Offcanvas opens/closes
   - Pills render correctly
   - Empty state shows
   - All buttons clickable
4. **Accessibility:**
   - Keyboard navigation (Tab, Enter, Escape)
   - Screen reader announces labels, buttons
   - Focus visible on all interactive elements
5. **Cross-browser:** Chrome, Firefox, Safari (iOS 13+)

---

## Rollback Plan

If Bootstrap breaks something:

1. Keep Pico CSS in version control (revert commit)
2. Keep Phase 2 in a separate branch
3. Use CDN for Bootstrap (fast to remove vs. npm rebuild)

---

## CSS Specificity Notes

Bootstrap uses `.btn`, `.form-control`, etc. extensively. If you have conflicting styles in `app.css`:

```css
/* app.css: make sure custom styles have higher specificity */

/* Before (generic) */
.badge { font-size: 0.7rem; }

/* After (specific to app) */
.txn-table .badge { font-size: 0.7rem; }
```

Or use `!important` sparingly for overrides Bootstrap can't change.

---

## Performance Impact

| Metric | Pico | Bootstrap | Impact |
|--------|------|-----------|--------|
| CSS size | 12 KB | 83 KB | +71 KB (gzip: +10 KB) |
| JS size | 0 KB | 30 KB | +30 KB (bundle incl. Popper) |
| Load time | <50ms | <100ms | Minor (cached after 1st load) |
| Lighthouse | 98/100 | 95/100 | Negligible for users |

**Mitigation:**
- Cache Bootstrap CDN aggressively (1 year expiry)
- Lazy-load phase2.js (not needed on non-filter pages)
- Minify custom CSS

---

## Backup: Pico + Bootstrap Hybrid

If you want to keep Pico for Phase 1:

```html
<!-- Load both, with Bootstrap loaded second -->
<link rel="stylesheet" href="/static/vendor/pico.min.css">
<link href="bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="/static/phase2.css">
```

Then use CSS scoping:
```css
/* app.css */
#txn-table { /* Pico styles */ }

/* phase2.css */
.offcanvas { /* Bootstrap + custom styles */ }
.active-filters-strip { /* Bootstrap utilities */ }
```

**Pro:** Minimal template changes
**Con:** CSS bloat, potential conflicts, harder to maintain

---

## Summary

**Recommended Path:** Option A (Full Bootstrap)
- Effort: 2–4 hours
- Risk: Low (Pico and Bootstrap are both CSS frameworks, no conflicts if done right)
- Benefit: Clean design system, easier to add features
- Timeline: Can be done in a single session

**Starting Point:**
1. Update `base.html` with Bootstrap CDN
2. Copy Phase 2 files (`phase2.css`, `phase2.js`)
3. Run through conversion checklist
4. Test each page
5. Commit and merge

---

## Questions?

- **"Will this break existing pages?"** Only if templates hardcode Pico class names. Bootstrap is a superset; if you use semantic HTML, bootstrap should enhance it.
- **"Can I do this incrementally?"** Yes! Convert one page at a time (Transactions → Rules → etc.)
- **"What about dark mode?"** Bootstrap 5.3 has built-in dark mode support via `data-bs-theme="dark"`. Pico has too; transition is smooth.
- **"Do I need to update the Python backend?"** No. This is pure frontend.
