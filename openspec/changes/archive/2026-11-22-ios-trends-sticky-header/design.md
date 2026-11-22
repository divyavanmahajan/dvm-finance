# Design

## Context

See `proposal.md` (Why). `TrendsView.matrix` builds the table as one vertical
`ScrollView`. Inside it, an `HStack` holds two halves:

- `frozenCategoryColumn`: a `VStack` with the "Category" header button, one
  cell for each row, and the "Total" cell.
- A horizontal `ScrollView` with `valueColumns`: a `Grid` whose first
  `GridRow` holds the month headers and the "Total" header.

Both headers are the first item of their half, so they scroll away with the
rows. Each value column has the same width, `MatrixMetrics.valueWidth`, and the
header row has the height `MatrixMetrics.headerHeight`. A `GeometryReader` in
the coordinate space of the horizontal scroll view already gives the
horizontal offset (`updateCategoryWidth(offset:)`). The deployment target is
iOS 17.

## Goals / Non-Goals

**Goals:**
- Keep the header row visible during a vertical scroll.
- Keep each month header exactly above its column during a horizontal scroll
  and during a change of the category width.

**Non-Goals:**
- No pinned "Total" row at the bottom.
- A horizontal drag on the header row does not scroll the months. The user
  scrolls the months in the body, as now.
- No change to the data, the cell taps, or the category column behavior.

## Decisions

### D1. Move the header row out of the vertical scroll view

`matrix` becomes a `VStack(spacing: 0)` with two parts:

1. **The header row:** an `HStack(spacing: 0)` with the "Category" header
   button (width `categoryWidth`) and a header strip. The strip is an
   `HStack` of the month headers and the "Total" header, each `valueWidth`
   wide, in a container that clips to its bounds.
2. **The body:** the current vertical `ScrollView`, without the two header
   items.

The header strip gets `.offset(x: -horizontalOffset)`. `horizontalOffset` is a
new `@State` that `updateCategoryWidth(offset:)` stores on each change, so one
reader drives both the header and the column width. The strip follows the raw
offset, also during a bounce, so each header stays above its column.

The strip is wider than the screen. It lies in an `.overlay` on a
`Color.clear` that takes the width the row gives it, and the overlay clips.
(A `.frame(maxWidth: .infinity)` around the fixed-size strip grew to the width
of the strip, so the whole tab became wider than the screen and shifted to the
left.)

Alternatives:
- *`LazyVStack(pinnedViews: [.sectionHeaders])`.* A pinned header must live in
  the outer vertical stack, outside the horizontal scroll view, so it needs
  the same offset sync. It also makes the body lazy, which changes the row
  alignment of the two halves. No gain.
- *A horizontal `ScrollView` for the header too, synced to the body.* Two
  scroll views that drive each other need `ScrollPosition`
  (iOS 18) or UIKit. Out of scope for iOS 17.
- *Swap the nesting (horizontal outside, vertical inside).* Then the frozen
  category column needs a vertical sync. Same problem in the other axis.

### D2. One source for the header sizes

The header cells use the same `valueCell` helper, `valueWidth`, `headerHeight`,
and `headerLines(period)` as today, so the widths match the body columns
exactly. The `Grid` in `valueColumns` loses its header `GridRow`.

### D3. Bounce and animation

The body bounces at the top and at the left edge. The header row is outside
the vertical scroll view, so a vertical bounce does not move it. During a
horizontal bounce, the strip moves with the columns and the clip hides what
is past the edge. A change of
the category width uses the same `withAnimation` for the header button and
the body column, so they move together.

## Risks / Trade-offs

- [The `onChange` of the offset runs after the layout pass, so the header can
  be one frame behind a fast horizontal scroll] → One frame at 60 or 120 Hz is
  not visible. The UI test checks the alignment after the scroll stops. If a
  lag shows on a device, a follow-up can move to `onScrollGeometryChange` when
  the deployment target is iOS 18.
- [A drag that starts on the header row does nothing horizontally] → The
  header row is short, and the body takes the drag. The non-goal records it.

## Migration Plan

No data change. The change ships in the next TestFlight build. To roll back,
revert the change in `TrendsView.swift`.
