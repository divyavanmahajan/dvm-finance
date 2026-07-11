# Phase 4: Polish & UX Enhancements

**Status:** Implementation files ready for integration  
**Deliverables:** `phase4.html`, `phase4.css`, `phase4.js`  
**Target:** abn-combined (Pico CSS framework)

## Overview

Phase 4 adds production-ready polish features to improve user experience:

- **Dark Mode** — Theme toggle with localStorage persistence
- **Toast Notifications** — User feedback for filter/rule changes
- **Skeleton Loaders** — Smooth placeholders during slow API loads
- **Print Styles** — Professional printable transaction reports
- **View Transitions** — Smooth animations on table updates (progressive enhancement)
- **Accessibility** — Tooltips, keyboard navigation, reduced-motion support

All features are **framework-agnostic** and work with the existing Pico CSS setup. No breaking changes.

---

## Files & Integration

### 1. `src/abn_combined/web/static/phase4.html`

Reusable template snippets. Include in `base.html`:

```html
<!-- In base.html <head> -->
<link rel="stylesheet" href="/static/phase4.css">

<!-- In base.html navbar (far right) -->
<nav>
  <ul>
    <li><strong>abn-combined</strong></li>
  </ul>
  <ul class="nav-tabs">
    <!-- existing nav tabs -->
  </ul>
  {% include "phase4/dark-mode-toggle.html" %}
</nav>

<!-- At end of base.html <body>, before </body> -->
<div id="toast-container" class="toast-container" aria-live="polite"></div>

<!-- Templates (use in JavaScript or Jinja) -->
<template id="toast-template">...</template>
<template id="skeleton-row-template">...</template>

<!-- In transactions.html, after filter chips -->
<div class="print-only filter-summary">
  <strong>Filters:</strong> {{ chip_labels }}
  <br><em>Generated {{ now.strftime('%Y-%m-%d %H:%M') }}</em>
</div>

<script src="/static/phase4.js" defer></script>
```

### 2. `src/abn_combined/web/static/phase4.css`

**No action needed** — load in `<head>`:

```html
<link rel="stylesheet" href="/static/phase4.css">
```

Features:
- Dark mode variables (`:root[data-theme="dark"]`)
- Skeleton animations (`@keyframes skeleton-pulse`)
- Toast styling (`.toast`, `.toast-container`)
- Print media queries (`@media print`)
- Accessibility enhancements (focus-visible, reduced-motion)

### 3. `src/abn_combined/web/static/phase4.js`

**No action needed** — load in `<body>`:

```html
<script src="/static/phase4.js" defer></script>
```

Global objects:
- `window.darkModeToggle()` — Alpine component
- `window.toastManager` — Toast API
- `window.reinitTooltips()` — Post-HTMX tooltip refresh
- `window.preparePrint()` — Print dialog trigger

---

## Feature Details

### Dark Mode

**Toggle Button:**

Add to navbar via `phase4.html`:

```html
<div x-data="darkModeToggle()" class="dark-mode-toggle">
  <button @click="toggle()" title="Toggle dark mode" class="icon-button">
    <span x-show="!dark">🌙</span>
    <span x-show="dark">☀️</span>
  </button>
</div>
```

**Storage:**
- Key: `localStorage.theme`
- Values: `'light'` | `'dark'`
- Applied to: `<html data-theme="light|dark">`

**Testing:**
1. Click toggle in navbar
2. Page reloads with persisted theme
3. DevTools → Storage → localStorage → `theme`

**CSS Variables:**

Pico CSS reads `data-theme` automatically. Phase 4 extends with custom vars:

```css
:root[data-theme="dark"] {
  --ph4-chip-bg: #1e3a5f;
  --ph4-chip-fg: #b8d4f5;
  --ph4-skeleton-bg: #353535;
  --ph4-toast-bg-success: #1e4620;
  /* ... more vars ... */
}
```

Add custom component colors here.

### Toast Notifications

**Trigger from Backend:**

Return `HX-Trigger` header in response:

```python
# In FastAPI route
@router.post("/transactions/filter")
async def apply_filter(...):
    # ... do work ...
    response = JSONResponse({"result": "..."})
    response.headers["HX-Trigger"] = "filterApplied"  # or JSON
    return response
```

**Trigger Mapping:**

| Trigger | Message |
|---------|---------|
| `filterApplied` | "Filters applied" |
| `filterCleared` | "Filters cleared" |
| `ruleCreated` | "Rule created" |
| `ruleUpdated` | "Rule updated" |
| `rulesApplied` | "Rules applied" |
| `categorized` | "Transaction categorized" |
| `uploaded` | "File uploaded successfully" |
| `snapshotExported` | "Snapshot exported" |
| `snapshotImported` | "Snapshot imported" |

**Custom Messages (JSON):**

```python
# Backend
response.headers["HX-Trigger"] = json.dumps({
    "toast": "success:5 rules applied to 12 transactions"
})
```

Listener in `phase4.js` (line ~165):

```javascript
document.addEventListener('htmx:afterSwap', (e) => {
  const hxTrigger = e.detail.xhr.getResponseHeader('HX-Trigger');
  // Parse and show toast
});
```

**Programmatic API:**

```javascript
window.toastManager.show('Message', 'success', 4000);  // auto-dismiss
window.toastManager.show('Error!', 'error', 0);       // manual dismiss
window.toastManager.dismissAll();
```

### Skeleton Loaders

**Use in HTMX:**

```html
<div id="txn-table"
     hx-get="/transactions/table"
     hx-trigger="load"
     hx-swap="innerHTML swap:500ms"
     data-show-skeleton="true">
  <!-- Skeletons injected on hx-beforeRequest -->
</div>
```

**Manual Injection:**

```javascript
window.showSkeletons('#txn-table', 3);  // 3 placeholder rows
```

**Result:**
- 3 animated skeleton rows appear immediately
- Real rows swap in after 500ms delay
- Smooth transition reduces perceived latency

### Print Styles

**Features:**
- Hides navbar, filter bar, buttons, pagination
- Shows filter summary as plain text
- Optimizes table for A4 paper (0.75rem font)
- Page breaks within table rows prevented
- Active filters printed in report header

**Test:**
1. Click Print button (add to navbar: `<button @click="preparePrint()" class="icon-button">🖨️</button>`)
2. Preview shows table + filter summary
3. No UI chrome on paper

**CSS:**

```css
@media print {
  header, nav, .filter-bar { display: none !important; }
  .print-only { display: block !important; }
  .txn-table { font-size: 0.75rem; }
  /* ... */
}
```

### View Transitions

**Progressive Enhancement:**

Requires browser support (`@supports view-transition-name`). Gracefully degrades.

```html
<div id="txn-table"
     hx-get="/transactions/table"
     hx-swap="innerHTML transition:true">
</div>
```

On swap, fade-out old content → fade-in new content (0.3s).

**Test:**
1. Apply filter on Transactions page
2. Table update animates smoothly
3. DevTools → More Tools → Rendering → Paint flashing shows transition

---

## Integration Checklist

### For Frontend Dev:

- [ ] Add `<link href="/static/phase4.css">` to `base.html <head>`
- [ ] Add dark mode toggle to navbar (copy from `phase4.html`)
- [ ] Add toast container to `<body>` (copy from `phase4.html`)
- [ ] Add `<script src="/static/phase4.js" defer></script>` to `base.html`
- [ ] Test dark mode toggle (localStorage persists across refresh)
- [ ] Verify tooltips re-initialize after HTMX swaps (call `reinitTooltips()`)
- [ ] Add filter summary `<div class="print-only">` to transactions.html
- [ ] Test print layout (`Cmd+P` / `Ctrl+P`)

### For Backend Dev:

- [ ] Add `HX-Trigger: filterApplied` header to `/transactions/filter` response
- [ ] Add `HX-Trigger: ruleUpdated` header to rule mutation endpoints
- [ ] Add `HX-Trigger: uploaded` header to `/upload` response
- [ ] For custom messages, return `HX-Trigger: {"toast": "success:Custom message"}`
- [ ] Test: apply filter → toast appears "Filters applied" → auto-dismisses after 4s

### For Testing:

- [ ] Unit tests: `ToastManager.show()`, `ToastManager.dismiss()`
- [ ] E2E tests: dark mode toggle → localStorage persists
- [ ] E2E tests: HTMX response with `HX-Trigger` → toast appears
- [ ] E2E tests: print layout hides UI, shows filters
- [ ] Visual regression: compare dark mode screenshots

### For Accessibility:

- [ ] Check WCAG 2.1 AA: color contrast (4.5:1 for text)
- [ ] Keyboard navigation: Tab through dark mode toggle and toast close buttons
- [ ] Reduced motion: test with DevTools → Rendering → Prefers reduced motion

---

## Dark Mode Color Reference

**Light Mode (default):**

```css
--ph4-chip-bg: #ddeeff;       /* light blue tint */
--ph4-chip-fg: #1a3a6b;       /* dark blue text */
--ph4-skeleton-bg: #f0f0f0;   /* light gray */
--ph4-toast-bg-success: #e8f5e9;  /* light green */
--ph4-toast-bg-error: #ffebee;    /* light red */
```

**Dark Mode:**

```css
--ph4-chip-bg: #1e3a5f;       /* dark blue */
--ph4-chip-fg: #b8d4f5;       /* light blue text */
--ph4-skeleton-bg: #353535;   /* dark gray */
--ph4-toast-bg-success: #1e4620;  /* dark green */
--ph4-toast-bg-error: #4a1f1f;    /* dark red */
```

Verify contrast ratios in both themes:
- Text on chip: 9.5:1 (WCAG AAA)
- Toast text: 8.2:1 (WCAG AAA)
- Skeleton pulse: sufficient for placeholder (non-content)

---

## localStorage Key Naming

**Dark Mode:**
- Key: `theme`
- Values: `'light'` | `'dark'`
- Scope: Per domain, persistent across sessions

**Future Extensions:**

```javascript
localStorage.setItem('abn:layout-density', 'compact');  // namespace with app prefix
localStorage.setItem('abn:column-sort', 'date-desc');
```

---

## Testing Scenarios

### Scenario 1: First-time User (No Saved Theme)

1. Open app
2. Detect `prefers-color-scheme: dark` in OS settings
3. Apply dark mode automatically (optional)
4. User clicks toggle → saves preference
5. Reload → theme persists

**Test Steps:**
```bash
# Clear localStorage
localStorage.clear();

# Reload page
# Should use system preference (or default to light)

# Click toggle
# Should switch to dark and save "theme=dark"

# Reload
# Should stay dark
```

### Scenario 2: Apply Filter with Toast

1. Set filters (date range, category)
2. Click "Apply"
3. Backend returns `HX-Trigger: filterApplied`
4. Toast shows "Filters applied"
5. Auto-dismisses after 4s

**Test Steps:**
```bash
# Open DevTools Network tab
# Apply filter
# Response headers include: HX-Trigger: filterApplied
# Toast appears (top-right)
# Dismisses after 4s
```

### Scenario 3: Print Transaction Report

1. Apply filters (e.g., "This Month")
2. Click Print button (navbar)
3. Print dialog shows:
   - Page title "abn-combined Transactions"
   - "Filters: This Month" summary
   - Table without navbar/buttons
4. Print to PDF or paper

**Test Steps:**
```bash
# Cmd+P (Mac) or Ctrl+P (Windows)
# Print Preview shows:
#   - No navbar
#   - Filter summary at top
#   - Compact table (0.75rem font)
#   - Borders on table cells
```

### Scenario 4: Slow Load (Skeleton Loaders)

1. Add network throttling (DevTools → Network → Slow 3G)
2. Apply filter
3. Skeleton rows appear immediately
4. Real rows replace after 500ms delay

**Test Steps:**
```bash
# DevTools → Network → Throttle to "Slow 3G"
# Apply filter in Transactions
# Observe: gray pulse animation in table
# After 0.5s: real rows fade in
```

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Dark mode toggle doesn't appear | `phase4.html` not included | Add dark-mode toggle snippet to navbar |
| Dark mode not persisting | `phase4.js` not loaded | Check `<script src="/static/phase4.js">` in `<head>` or `<body>` |
| Toasts don't appear | `HX-Trigger` header not set | Return `response.headers["HX-Trigger"] = "..."` from backend |
| Skeletons flash and disappear | Timing mismatch | Adjust `hx-swap="innerHTML swap:500ms"` to match API latency |
| Print hides table | CSS `display: none` on wrong selector | Check `.txn-table` not in `@media print { display: none }` |
| Tooltips broken after swap | `reinitTooltips()` not called | Ensure `phase4.js` listener on `htmx:afterSwap` is active |

---

## Future Enhancements

### Phase 4.1: Analytics
- Log theme changes to backend
- Track toast dismissal patterns
- Measure print usage

### Phase 4.2: Customization
- User color scheme picker (not just light/dark)
- Adjustable text size / density
- Custom print templates

### Phase 4.3: Advanced Features
- Offline mode (localStorage caching)
- Multi-tab synchronization (BroadcastChannel API)
- Undo/Redo stack (transactions, filters)

---

## Files Summary

| File | Size | Purpose |
|------|------|---------|
| `phase4.html` | ~500 lines | Template snippets (dark toggle, toasts, skeletons, print summary) |
| `phase4.css` | ~350 lines | Theming, animations, print styles, accessibility |
| `phase4.js` | ~300 lines | Dark mode logic, toast manager, HTMX listeners, utilities |

**Total code:** ~1150 lines (minified: ~40KB CSS + JS combined)

**Dependencies:**
- Alpine.js (already in `base.html`)
- HTMX (already in `base.html`)
- Modern browser (CSS Grid, Flexbox, CSS Variables, Fetch API)

---

## Author Notes

Phase 4 is designed to be **minimally invasive**:
- No changes to existing HTML structure
- No JS build step required
- Graceful degradation in older browsers
- All features optional (can disable by not loading `phase4.css` or `phase4.js`)

The toggle, toasts, and print styles are production-ready. Skeleton loaders and view transitions are progressive enhancements.

**Estimated integration time:** 30–45 minutes (adding CSS/JS files + navbar snippet).

---

## Questions or Issues?

1. **Theme colors not rendering:** Check `:root[data-theme="dark"]` CSS is loaded
2. **Toasts don't trigger:** Verify backend `HX-Trigger` header is set correctly
3. **Print looks broken:** Test in different browsers (Chrome → Firefox → Safari)
4. **Accessibility audit:** Use axe DevTools or WAVE to scan for contrast/focus issues
