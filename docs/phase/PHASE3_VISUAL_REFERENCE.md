# Phase 3: Visual Reference Guide

This document provides visual diagrams and layout examples for Phase 3 components.

---

## Component 1: Category Checkbox-Dropdown

### Closed State
```
┌──────────────────────────────────────┐
│ Categories [v]                      │
└──────────────────────────────────────┘
```

### Open State (Empty Search)
```
┌──────────────────────────────────────┐
│ Categories [v]                      │
├──────────────────────────────────────┤
│ 🔍 [Search categories…]             │
├──────────────────────────────────────┤
│ ☐ Uncategorized                    │
│ ☐ Groceries                        │
│ ☐ Transport                        │
│ ☐ Utilities                        │
│ ☐ Entertainment                    │
│ ☐ Eating Out                       │
│ ☐ Healthcare                       │
│ ☐ Subscriptions                    │
│ ☐ Travel                           │
│ ☑ Salaries                         │  ← Selected (highlighted)
└──────────────────────────────────────┘
```

### Open State (With Search)
```
┌──────────────────────────────────────┐
│ 3 selected [v]                      │  ← Button text updates
├──────────────────────────────────────┤
│ 🔍 [Search categ…]                  │
│     ↑ (user types "gro")            │
├──────────────────────────────────────┤
│ ☑ Groceries                        │
│                                      │
│ No categories match your search.   │  ← When no results
└──────────────────────────────────────┘
```

### Button Text States

| State | Text |
|-------|------|
| No categories selected | "Categories" |
| 1 category selected | "1 selected" |
| 2 categories selected | "2 selected" |
| All categories selected | "All categories" |

### Size Reference

| Screen | Dropdown Width | Max Height | Behavior |
|--------|----------------|------------|----------|
| Mobile (<576px) | ~90% container | 200px | Scrollable, full-width |
| Tablet (576–768px) | 18rem | 250px | Normal dropdown |
| Desktop (768px+) | 18rem | 20rem | Normal dropdown |

---

## Component 2: Bootstrap Pagination

### Standard Pagination (5+ pages)
```
┌─────────────────────────────────────────────────────┐
│  Prev   1   2   •   4   5   6   •   10   Next      │
│            (Page 5 highlighted)                     │
│                                                     │
│               Page 5 of 10                          │
└─────────────────────────────────────────────────────┘
```

### Pagination States

```
First page (disabled Previous):
┌─────────────────────────────────────────────┐
│  [Prev]  ●1   2   3  ...  10   Next         │
│  (faded)                                    │
└─────────────────────────────────────────────┘

Middle page (all enabled):
┌─────────────────────────────────────────────┐
│  Prev   1  ...  4   ●5   6  ...  10   Next  │
└─────────────────────────────────────────────┘

Last page (disabled Next):
┌─────────────────────────────────────────────┐
│  Prev   1  ...  8   9   ●10  [Next]         │
│                              (faded)        │
└─────────────────────────────────────────────┘
```

### Responsive Sizes

```
Desktop (lg+):
Prev  1  2  3  4  5  ...  10  Next
Page 3 of 10

Tablet (md):
Prev  1  2  3  ...  10  Next
Page 3 of 10

Mobile (sm):
Prev  1  ...  10  Next
Page 3 of 10

Extra small (xs):
[Prev] [1] [10] [Next]  (stacked or condensed)
Page 3 of 10
```

### Color States

```
Inactive (default):
┌──────┐
│  1   │  ← Gray border, normal text
└──────┘

Hover (not current):
┌──────┐
│  1   │  ← Teal border, teal bg on hover
└──────┘

Current page:
┌──────┐
│ ●2   │  ← Teal bg, white text, bold
└──────┘

Disabled (at boundary):
┌──────┐
│[Prev]│  ← Faded (opacity: 0.5)
└──────┘

Ellipsis:
┌──────┐
│  …   │  ← Disabled state (not clickable)
└──────┘
```

---

## Component 3: Mobile Card Layout

### Desktop View (md+ / ≥768px)

```
┌─────────────────────────────────────────────────────────────────┐
│ TABLE LAYOUT                                                     │
├──┬──────────┬──────────┬────────────────┬──────┬──────┬──────┬────┤
│  │ Date     │ Account  │ Description    │ Amt  │ Cat  │ Tags │    │
├──┼──────────┼──────────┼────────────────┼──────┼──────┼──────┼────┤
│▸ │2026-07-08│NL91AB... │Albert Heijn... │-43.17│Groc. │shop  │ + r│
│  │          │          │(AHNH 1653)     │      │      │      │    │
├──┴──────────┴──────────┴────────────────┴──────┴──────┴──────┴────┤
│ Full detail expanded inline when ▸ clicked                       │
└─────────────────────────────────────────────────────────────────┘
```

**Table Features:**
- Multi-column headers (Date, Account, Description, Amount, Category, Tags, Source, Actions)
- Hover effect on rows (light background)
- Expandable detail row via toggle button
- Inline edit buttons for category/tags

### Mobile View (<md / <768px)

```
┌─────────────────────────────────────┐
│ CARD LAYOUT (Stacked)               │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ 2026-07-08      Amount: −€ 43.17│ │
│ ├─────────────────────────────────┤ │
│ │ Albert Heijn 1653 (bold)        │ │
│ │ Category: Groceries             │ │
│ │ Account: NL91ABNA…              │ │
│ │ Source: rule #42                │ │
│ ├─────────────────────────────────┤ │
│ │ [Show detail]  [+ rule]         │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ 2026-07-07      Amount: +€125.50│ │  ← Green (income)
│ ├─────────────────────────────────┤ │
│ │ ABC Bank Transfer               │ │
│ │ Category: Salaries              │ │
│ │ Account: NL91ABNA…              │ │
│ ├─────────────────────────────────┤ │
│ │ [Show detail]  [+ rule]         │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ 2026-07-06      Amount: −€ 12.99│ │
│ ├─────────────────────────────────┤ │
│ │ Netflix NL                      │ │
│ │ Category: Subscriptions         │ │
│ │ Account: NL91ABNA…              │ │
│ │ Detail open:                    │ │
│ │ ├─ Full Description: Netflix... │ │
│ │ ├─ Amount: −12.99 EUR           │ │
│ │ └─ Tags: streaming, monthly     │ │
│ ├─────────────────────────────────┤ │
│ │ [Hide detail]  [+ rule]         │ │
│ └─────────────────────────────────┘ │
│                                     │
└─────────────────────────────────────┘
```

**Card Features:**
- Date + Amount in header (right-aligned)
- Description prominent (bold)
- Category badge with inline edit
- Account and tags visible
- Expandable detail section (tap to toggle)
- Action buttons at bottom

### Card Anatomy

```
┌─────────────────────────────────────┐
│ 2026-07-08    Amount: −€ 43.17     │  ← Card Header
│ (Date)        (Amount with color)   │
├─────────────────────────────────────┤
│ Albert Heijn 1653 (bold)            │
│ Category: [Groceries] [M]           │  ← Card Body
│ Account: NL91ABNA…                  │  (Label: Value pairs)
│ Tags: shopping, weekly              │
│ Source: rule #42                    │
│                                     │
│ Full Description: ...               │  ← Card Detail
│ Amount: −43.17 EUR                  │  (Expandable)
│ Date: 2026-07-08                    │
│ …                                   │
├─────────────────────────────────────┤
│ [Show detail]    [+ rule]           │  ← Card Footer
│                                     │  (Action buttons)
└─────────────────────────────────────┘
```

### Responsive Stacking

```
Extra Small (xs < 576px):
┌─────────────┐
│ 2026-07-08  │
│ −€ 43.17    │  ← Stacked vertically
│ ─────────── │
│ Albert...   │
│ Category... │
├─────────────┤
│ [Show detail]
└─────────────┘

Small (sm 576–768px):
┌────────────────────────────┐
│ 2026-07-08  Amount: −€ 43.17│  ← Date left, amount right
├────────────────────────────┤
│ Albert Heijn 1653          │
│ Category: Groceries        │
│ Account: NL91ABNA…         │
├────────────────────────────┤
│ [Show detail] [+ rule]     │
└────────────────────────────┘

Medium+ (md ≥ 768px):
→ TABLE VIEW ONLY
Cards hidden, table shown
```

### Color Coding

```
Positive Amount (Income):
Amount: +€ 125.50  ← Green (#1b5e20)

Negative Amount (Expense):
Amount: −€ 43.17   ← Red (#c62828)

Uncategorized Badge:
[Uncategorized]    ← Gray (#e0e0e0)

Manual Category Badge:
[Groceries] [M]    ← M = yellow (#ffc107)

Category Badge (Normal):
[Groceries]        ← Teal (#1a5f7a, matching primary)
```

---

## Responsive Filter Panel

### Desktop View (lg+, 1200px+)

```
┌────────────────────────────────────────────────────────┐
│ OFFCANVAS ADVANCED FILTERS (4 Columns)                 │
├────────────────────────────────────────────────────────┤
│                                                        │
│ Col 1                Col 2              Col 3  Col 4  │
│ ──────────────────── ──────────────────               │
│ Date Range:          Amount Range:      Account:      │
│ [From]  [To]        €[Min]  €[Max]     [Select▼]    │
│                                                        │
│ Categories:          Exclude Categories:              │
│ [Categories ▼]      [Exclude ▼]                      │
│ (Type to search)                                       │
│                                                        │
│                      Tags:                            │
│                      [Tags ▼]                         │
│                      (Ctrl+Click for multi)           │
│                                                        │
├────────────────────────────────────────────────────────┤
│ [← Close]           [Reset]           [Apply]         │
└────────────────────────────────────────────────────────┘
```

### Tablet View (md+, 768px+)

```
┌────────────────────────────────────┐
│ OFFCANVAS ADVANCED FILTERS (2 Cols)│
├────────────────────────────────────┤
│                                    │
│ Col 1              Col 2           │
│ ──────────────────               │
│ Date Range:        Categories:    │
│ [From]  [To]      [Categories ▼] │
│                                    │
│ Amount Range:      Exclude:       │
│ €[Min]  €[Max]    [Exclude ▼]   │
│                                    │
│ Account:           Tags:           │
│ [Select▼]        [Tags ▼]        │
│                                    │
├────────────────────────────────────┤
│ [Reset]        [Apply]             │
└────────────────────────────────────┘
```

### Mobile View (< 768px)

```
┌─────────────────────────────┐
│ OFFCANVAS (1 Column, Full)  │
├─────────────────────────────┤
│                             │
│ Date Range:                 │
│ [From]  [To]               │
│                             │
│ Amount Range:               │
│ €[Min]  €[Max]            │
│                             │
│ Account:                    │
│ [Select▼]                  │
│                             │
│ Categories:                 │
│ [Categories ▼]             │
│ (Type to search)            │
│                             │
│ Exclude Categories:         │
│ [Exclude ▼]                │
│                             │
│ Tags:                       │
│ [Tags ▼]                   │
│                             │
├─────────────────────────────┤
│ [Reset]                     │  ← Stacked
│ [Apply]                     │  (full-width)
└─────────────────────────────┘
```

---

## Active Filter Pills Strip

### Empty State (No Filters)
```
(Nothing shown)
```

### With Filters
```
┌─────────────────────────────────────────────────────────┐
│  ●[Date: This Month ×]  ●[Amount: < €100 ×]            │
│                                                         │
│  ●[Category: Groceries ×]  [Clear all]                 │
└─────────────────────────────────────────────────────────┘
```

### Mobile (Wrapping)
```
┌──────────────────────────────┐
│ ●[Date: This ×] ●[Amount: <€ ×] │
│ ●[Category: ×]  [Clear all]   │
└──────────────────────────────┘
```

---

## Pagination States & Interactions

### State Machine

```
                    ┌─────────────┐
                    │   Page 1    │
                    │ Prev:Disabled│
                    └────────┬────┘
                             │
                      User clicks "2"
                             │
                             ▼
                    ┌─────────────┐
                    │   Page 2    │
                    │ Prev:Enabled│
                    └────────┬────┘
                             │
                      User clicks "Next"
                             │
                             ▼
                    ┌─────────────┐
                    │   Page N    │
                    │ Next:Enabled│
                    └────────┬────┘
                             │
            User clicks "N+1" (last page)
                             │
                             ▼
                    ┌─────────────┐
                    │  Last Page  │
                    │ Next:Disabled│
                    └─────────────┘
```

### URL Changes

```
Initial load:
/transactions

Select category filter:
/transactions?category=Groceries

Navigate to page 2:
/transactions?category=Groceries&page=2

Add date filter:
/transactions?category=Groceries&page=1&preset=last-7-days

(Page resets to 1 when filters change)
```

---

## Dark Mode Comparison

### Light Mode (Default)
```
┌─────────────────────────┐
│ Background: #fff        │
│ Text: #333 (dark)       │
│ Border: #ddd (light)    │
│                         │
│ [Categories ▼]         │  ← White button
│ ☐ Groceries            │  ← White dropdown
│                         │
│ Amount: −€43.17         │  ← Red text
│ Amount: +€125.50        │  ← Green text
└─────────────────────────┘
```

### Dark Mode
```
┌─────────────────────────┐
│ Background: #252525     │
│ Text: #e0e0e0 (light)   │
│ Border: #444 (dark)     │
│                         │
│ [Categories ▼]         │  ← Dark button
│ ☐ Groceries            │  ← Dark dropdown
│                         │
│ Amount: −€43.17         │  ← Light red
│ Amount: +€125.50        │  ← Light green
└─────────────────────────┘
```

**Colors Used in Dark Mode:**
- `.txn-card`: `#252525` (background), `#e0e0e0` (text)
- `.dropdown-menu`: `#2d2d2d` (background)
- `.badge`: `#1e3a5f` (background), `#b8d4f5` (text)
- Amount colors: lighter shades of green/red

---

## Breakpoint Testing Grid

### xs (< 576px) — iPhone SE
```
Width: 375px
[S] [M] [L] [XL] [XXL]
 ✓
 
Card layout: YES
Table layout: NO
Filter columns: 1
Pagination: Condensed
```

### sm (576–768px) — iPhone 12
```
Width: 390px
[S] [M] [L] [XL] [XXL]
   ✓
   
Card layout: YES (until 768px)
Table layout: NO
Filter columns: 1
Pagination: Normal
```

### md (768–992px) — iPad
```
Width: 768px
[S] [M] [L] [XL] [XXL]
       ✓
       
Card layout: NO (switches at md)
Table layout: YES
Filter columns: 2
Pagination: Normal
```

### lg (992–1200px) — Desktop
```
Width: 1024px
[S] [M] [L] [XL] [XXL]
           ✓
           
Card layout: NO
Table layout: YES
Filter columns: 2
Pagination: Normal
```

### xl (1200–1400px) — Large Desktop
```
Width: 1200px
[S] [M] [L] [XL] [XXL]
               ✓
               
Card layout: NO
Table layout: YES
Filter columns: 4
Pagination: Normal
```

### xxl (1400px+) — Extra Large
```
Width: 1600px
[S] [M] [L] [XL] [XXL]
                   ✓
                   
Card layout: NO
Table layout: YES
Filter columns: 4
Pagination: Normal
```

---

## Interaction Flows

### Category Selection Flow

```
User sees dropdown button
        ↓
    "Categories"
        ↓
User clicks to open
        ↓
▼ Dropdown expands
  ☐ Uncategorized
  ☐ Groceries
  ☐ Transport
  ☐ Utilities
  ☑ Entertainment     (checked)
  ☐ Eating Out
        ↓
User types "trans" in search
        ↓
▼ List filters in real-time
  ☐ Transport        (matching)
        ↓
User clicks checkbox next to "Transport"
        ↓
  ✓ Button text updates to "2 selected"
  ✓ Hidden form checkboxes updated
  ✓ HTMX triggered
        ↓
Server filters transactions
        ↓
Table/Cards re-render with filtered data
        ↓
URL updates: ?category=Entertainment&category=Transport
```

### Pagination Flow

```
User sees results on page 1
        ↓
Pagination shows: Prev  1  2  3  ...  10  Next
                       ↑
                    (current)
        ↓
User clicks "3"
        ↓
▼ Page button highlights
Prev  1  2  3  ...  10  Next
              ↑
           (current)
        ↓
GET /transactions/table?page=3&...
        ↓
Server returns new rows for page 3
        ↓
Table/Cards replace with new data
        ↓
URL updates: ?page=3
```

### Mobile Card Expand/Collapse

```
User sees card with "[Show detail]" button
        ↓
┌─ 2026-07-08  Amount: −€43.17
│ Albert Heijn 1653
│ Category: Groceries
│ [Show detail]  [+ rule]
        ↓
User taps "[Show detail]"
        ↓
▼ Card expands, button text changes
┌─ 2026-07-08  Amount: −€43.17
│ Albert Heijn 1653
│ Category: Groceries
│ Account: NL91ABNA…
│ Tags: shopping, weekly
│ Source: rule #42
│ 
│ Full Description: Albert Heijn…
│ Amount: −43.17 EUR
│ Date: 2026-07-08
│ [Hide detail]  [+ rule]
        ↓
User taps "[Hide detail]"
        ↓
▼ Card collapses back to normal
┌─ 2026-07-08  Amount: −€43.17
│ Albert Heijn 1653
│ Category: Groceries
│ [Show detail]  [+ rule]
```

---

## Testing Checklist with Visuals

### Category Picker ✓
- [ ] Dropdown opens (visually expands below button)
- [ ] Search input visible and focusable
- [ ] Checkboxes show/hide based on search
- [ ] Button text changes: "Categories" → "N selected" → "All categories"
- [ ] Selected items have checkmark
- [ ] Dropdown stays open while interacting (data-bs-auto-close="outside")
- [ ] Close on outside click or Escape key

### Pagination ✓
- [ ] Previous button disabled on page 1 (visually faded)
- [ ] Next button disabled on last page (visually faded)
- [ ] Current page highlighted in blue/teal (`.active` state)
- [ ] Ellipsis appears for gaps (e.g., "1 … 5 6 7 … 10")
- [ ] Clicking page number updates table
- [ ] URL updates with new page number
- [ ] "Page N of M" text updates correctly

### Mobile Cards ✓
- [ ] Cards display below 768px, table hidden
- [ ] Cards have clear borders and shadows
- [ ] Amount color-coded (red for negative, green for positive)
- [ ] Category badge visible
- [ ] Detail section expands/collapses smoothly
- [ ] Buttons at bottom are full-width and stacked
- [ ] Text wraps appropriately on narrow screens
- [ ] Dark mode text is readable

### Responsive Filters ✓
- [ ] Filters stack vertically on mobile (<768px)
- [ ] Filters use 2 columns on tablet (768–1200px)
- [ ] Filters use 4 columns on desktop (≥1200px)
- [ ] Offcanvas buttons stack full-width on mobile
- [ ] Form controls stretch to available width
- [ ] No horizontal overflow on mobile

---

**End of Visual Reference Guide**

For implementation details, see `PHASE3_IMPLEMENTATION_NOTES.md`
For integration steps, see `PHASE3_INTEGRATION_GUIDE.md`
