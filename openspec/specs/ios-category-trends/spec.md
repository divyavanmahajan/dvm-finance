# iOS Category Trends Specification

## Purpose

The trends tab shows the spend for each category across time on the phone. Each
cell opens the transactions behind its value.

## Requirements

### Requirement: Matrix of category against period
The trends tab SHALL show a scrollable matrix of the effective category against
the period. The app SHALL roll each category up to its top-level segment. The
app SHALL let the user expand a group into its exact child categories. The
default window is the last 12 months. The matrix SHALL use compact columns: the
width of a value column SHALL fit its widest value, with a small fixed gap.

#### Scenario: The user opens the trends tab
- **WHEN** the user opens the trends tab
- **THEN** the app shows the last 12 months

#### Scenario: The user expands a group
- **WHEN** the user expands a rolled-up category row
- **THEN** the app lists the exact child categories with their own values

#### Scenario: The header of a month column
- **WHEN** the matrix shows month periods
- **THEN** each month header shows the short month name on the first line and
  the year on the second line, so the header is not wider than the values

#### Scenario: A value is large
- **WHEN** a cell holds the widest compact value, for example "-999.9K"
- **THEN** the app shows the full value on one line, and it does not truncate
  the value

### Requirement: Period selection
The app SHALL let the user change the reported period. The app SHALL use the
same sign conventions as the trends of the desktop application.

#### Scenario: The user selects a different period
- **WHEN** the user selects a different period
- **THEN** the app computes the matrix again across that window

### Requirement: Exact sums behind each cell
A tap on a cell SHALL open the transactions screen with the equivalent filter.
The sum of the listed transactions SHALL equal the value of the cell.

#### Scenario: The user taps a cell
- **WHEN** the user taps the cell of one category and one month
- **THEN** the transactions screen lists the transactions of that category in
  that month

### Requirement: Transfer exclusion with a toggle
The trends tab SHALL exclude the transfer categories by default. It SHALL
identify a transfer by the transfer prefix. It SHALL offer a toggle that applies
for the session.

#### Scenario: The user turns the transfers toggle on
- **WHEN** the user turns the transfers toggle on
- **THEN** the transfer categories appear in the matrix until the user turns the
  toggle off

### Requirement: A table, and not a chart
The app SHALL show the trends as a table. The app SHALL NOT draw a chart.

#### Scenario: The app shows the trends tab
- **WHEN** the app shows the trends tab
- **THEN** the data is a table of numbers

### Requirement: Category column width follows the scroll
While the value columns are at their start position, the category column SHALL
show each category name in full. After the user scrolls the value columns to
the right, the category column SHALL become narrow.

#### Scenario: The user opens the trends tab on an iPhone
- **WHEN** the user opens the trends tab
- **THEN** the category column is wide enough for the longest category name,
  up to half the screen width, and the app truncates only a name that is wider
  than that limit

#### Scenario: The user scrolls the months to the right
- **WHEN** the user scrolls the value columns to the right in portrait on an
  iPhone with a screen width of 390 points or more
- **THEN** the category column becomes narrow, the app truncates a long
  category name at the end, and the matrix shows at least four value columns

#### Scenario: The user scrolls back to the start
- **WHEN** the user scrolls the value columns back to the start position
- **THEN** the category column becomes wide again and shows each name in full

### Requirement: Full category name on request
The app SHALL show the full name of a category when the user long-presses a
category name. The app SHALL show the full name in a popover. While the column
does not stay wide, the popover SHALL also tell the user that a tap on the
"Category" header shows all names in full. A tap on a category row SHALL keep
its current function: it expands or collapses a group.

#### Scenario: The user long-presses a truncated name
- **WHEN** the category column truncates a name, and the user long-presses
  that name
- **THEN** the app shows the full name in a popover, and the popover closes
  when the user taps outside it

#### Scenario: The popover tells the user how to see all names
- **WHEN** the popover shows a full name, and the column does not stay wide
- **THEN** the popover also shows the hint "Tap Category to show all names"
  below the name

#### Scenario: The column already stays wide
- **WHEN** the popover shows a full name, and the column stays wide
- **THEN** the popover shows the full name only, without the hint

#### Scenario: The user taps a group row
- **WHEN** the user taps the name of a rolled-up category row
- **THEN** the app expands or collapses the group, and it shows no popover

#### Scenario: The full name for VoiceOver
- **WHEN** VoiceOver reads a category cell
- **THEN** VoiceOver reads the full name, and not the truncated text

### Requirement: Middle truncation of a category name
When the app truncates a category name, it SHALL truncate it in the middle, so
that the start and the end of the name stay visible.

#### Scenario: A long child name in the narrow column
- **WHEN** the narrow category column shows a child name that is too long
- **THEN** the app shows the start and the end of the name, with an ellipsis
  in the middle

### Requirement: Keep the category column wide
A tap on the "Category" header SHALL keep the category column wide. A second
tap SHALL return the column to the automatic width. While the column stays
wide, a horizontal scroll SHALL NOT make it narrow. The header SHALL show an
icon for the current state. The app SHALL keep the state while the trends tab
stays open.

#### Scenario: The user keeps the column wide
- **WHEN** the user taps the "Category" header and then scrolls the months to
  the right
- **THEN** the category column stays wide and shows each name in full

#### Scenario: The user returns to the automatic width
- **WHEN** the column stays wide, and the user taps the "Category" header again
- **THEN** the column becomes narrow again after a scroll to the right
