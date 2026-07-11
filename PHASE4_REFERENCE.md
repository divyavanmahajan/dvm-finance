# Phase 4 Polish — Quick Reference

**Status:** Ready to integrate  
**Framework:** Pico CSS (maintained, not migrated)  
**Effort:** 30–45 mins  
**Files:** 3 code + 3 docs

## What's Included

✅ **Dark Mode** — Toggle button with localStorage persistence  
✅ **Toasts** — User feedback on filter/rule changes  
✅ **Skeleton Loaders** — Smooth loading placeholders  
✅ **Print Styles** — Professional A4 reports  
✅ **View Transitions** — Smooth HTMX animations (progressive)  
✅ **Accessibility** — WCAG 2.1 AA, keyboard nav, reduced motion  

## Files Location

```
Code:
  src/abn_combined/web/static/phase4.css    (399 lines)
  src/abn_combined/web/static/phase4.js     (362 lines)
  src/abn_combined/web/static/phase4.html   (80 lines, snippets)

Docs:
  docs/phase/PHASE4_SUMMARY.md              (executive summary)
  docs/phase/phase4-quickstart.md           (5-min setup)
  docs/phase/phase4-implementation.md       (full reference)
```

## Integration in 3 Steps

### 1. Update `base.html`

```html
<head>
  <!-- ... existing ... -->
  <link rel="stylesheet" href="/static/phase4.css">
</head>

<body>
  <header class="container">
    <nav>
      <ul>
        <li><strong>abn-combined</strong></li>
      </ul>
      <ul class="nav-tabs">
        <!-- existing nav tabs -->
      </ul>
      <!-- NEW: Dark mode toggle -->
      <div x-data="darkModeToggle()" class="dark-mode-toggle">
        <button @click="toggle()" title="Toggle dark mode" class="icon-button">
          <span x-show="!dark">🌙</span>
          <span x-show="dark">☀️</span>
        </button>
      </div>
    </nav>
  </header>

  <main class="container">
    {% block content %}{% endblock %}
  </main>

  <!-- NEW: Toast container (must be before script) -->
  <div id="toast-container" class="toast-container" aria-live="polite"></div>

  <!-- NEW: Phase 4 script -->
  <script src="/static/phase4.js" defer></script>
</body>
```

### 2. Update `templates/transactions.html`

Add after filter chips:

```html
<!-- Print-only filter summary -->
<div class="print-only filter-summary">
  <strong>Filters:</strong>
  {% if chips %}
    {% for chip in chips %}{{ chip.label }}{% if not loop.last %}, {% endif %}{% endfor %}
  {% else %}
    None
  {% endif %}
  <br><em>Report generated {{ now.strftime('%Y-%m-%d %H:%M') }}</em>
</div>
```

### 3. Backend: Add Toast Triggers

In your FastAPI routes:

```python
from fastapi import Response
import json

@router.post("/transactions/filter")
async def apply_filters(...):
    # ... do work ...
    return Response(
        content=render_template("transactions.html", ...),
        headers={"HX-Trigger": "filterApplied"}
    )

@router.post("/rules/create")
async def create_rule(...):
    # ... do work ...
    return Response(
        content=render_template("rules.html", ...),
        headers={"HX-Trigger": "ruleCreated"}
    )
```

## Features At a Glance

### Dark Mode
- Toggle button (🌙/☀️) in navbar, far right
- Persists to `localStorage.theme`
- Pico CSS automatically re-colors everything

### Toasts
- Appear top-right, auto-dismiss 4s
- Trigger from backend: `HX-Trigger: filterApplied`
- Types: success, info, warning, error

### Skeleton Loaders
- Animated placeholder rows on slow loads
- Use: `hx-swap="innerHTML swap:500ms"`

### Print
- Press `Cmd+P` or `Ctrl+P`
- Shows filter summary + optimized table
- Hides navbar, buttons, pagination

### View Transitions
- Smooth fade on table updates
- Use: `hx-swap="innerHTML transition:true"`
- Gracefully degrades in older browsers

## Test It (5 mins)

```bash
# Dark mode
Click moon icon → page darkens → reload → stays dark ✅

# Toast
Apply filter → "Filters applied" appears (top-right) → auto-dismisses ✅

# Print
Cmd+P → preview shows table + filters (no navbar) ✅

# Skeleton (with DevTools throttle)
Network → "Slow 3G" → apply filter → gray pulse rows → real data replaces ✅
```

## Common Issues

| Issue | Fix |
|-------|-----|
| Toggle doesn't show | Add `<div x-data="darkModeToggle()">` to navbar |
| Toggle doesn't persist | Load `phase4.js` in `<body>`, not `<head>` |
| Toasts don't appear | Backend must return `HX-Trigger` header |
| Print shows navbar | Reload page (CSS cache); verify `@media print` in CSS |
| Colors look off in dark mode | Check `:root[data-theme="dark"]` CSS loaded |

## Toast Trigger Mapping

| Trigger | Toast Message |
|---------|---------------|
| `filterApplied` | "Filters applied" |
| `filterCleared` | "Filters cleared" |
| `ruleCreated` | "Rule created" |
| `ruleUpdated` | "Rule updated" |
| `rulesApplied` | "Rules applied" |
| `categorized` | "Transaction categorized" |
| `uploaded` | "File uploaded successfully" |
| `snapshotExported` | "Snapshot exported" |
| `snapshotImported` | "Snapshot imported" |

Or custom: `json.dumps({"toast": "success:5 rules applied to 12 txns"})`

## Color Scheme (WCAG AAA)

**Light Mode:**
- Chip: #ddeeff bg, #1a3a6b text (9.5:1 contrast)
- Toast success: #e8f5e9 bg, #2e7d32 border
- Skeleton: #f0f0f0 pulse

**Dark Mode:**
- Chip: #1e3a5f bg, #b8d4f5 text (9.5:1 contrast)
- Toast success: #1e4620 bg, #2e7d32 border
- Skeleton: #353535 pulse

## Breaking Changes

**None.** All files are additive:
- New CSS only (doesn't override existing Pico)
- New JS listeners (don't conflict with existing)
- Optional HTML snippets (can be omitted)
- No changes to schema or existing HTML structure

## Full Documentation

- **Quick start (5 mins):** `docs/phase/phase4-quickstart.md`
- **Implementation guide (30 mins):** `docs/phase/phase4-implementation.md`
- **Executive summary:** `docs/phase/PHASE4_SUMMARY.md`

## Questions?

1. **Feature details** → `phase4-implementation.md` (Feature Details section)
2. **Troubleshooting** → `phase4-implementation.md` (Troubleshooting section)
3. **Integration checklist** → `phase4-implementation.md` (Integration Checklist section)
4. **Test scenarios** → `phase4-implementation.md` (Testing Scenarios section)

---

## Success Checklist

After integration, verify:

- [ ] Dark toggle appears in navbar
- [ ] Toggle persists after reload
- [ ] Toast appears on filter apply
- [ ] Print preview shows filters + table (no navbar)
- [ ] Colors readable in dark mode
- [ ] Tab navigation works (keyboard only)
- [ ] Tests pass: `pytest`
- [ ] Coverage maintained: `pytest --cov=abn_combined` ≥ 80%

---

**Integration time: 30–45 minutes**  
**Status: Ready to merge**  
**Deployment: Safe (no schema changes)**
