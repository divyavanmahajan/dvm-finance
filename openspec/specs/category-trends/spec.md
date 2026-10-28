# Category Trends Specification

## Purpose

The trends table shows the spend for each category across time. Each cell links
to the exact transactions behind it. The user can therefore trace a number to
its rows.

## Requirements

### Requirement: Matrix of category against period
The system SHALL sum the transaction amounts by the effective category and the
period across the window. It SHALL use one grouped database query. It SHALL
report a column total for each period and a grand total.

#### Scenario: The window spans three months
- **WHEN** the window spans three months, and two categories have spend
- **THEN** the table holds one column for each month, one row for each category
  group, the column totals, and the grand total

### Requirement: Granularity
The system SHALL support a monthly and a yearly granularity. The default is
monthly. The system SHALL fall back to monthly for an unknown value.

#### Scenario: The user selects the yearly granularity
- **WHEN** the user selects the yearly granularity
- **THEN** each column covers one calendar year, and the system clamps the
  columns to the window

### Requirement: Default window
With no date parameter, the window SHALL span the last 12 calendar months, and
it SHALL end on today. The table therefore holds the current month, which is
still in progress.

#### Scenario: The user opens the page in March
- **WHEN** the user opens the trends page on 15 March
- **THEN** the window ends on 15 March and starts on 1 April of the previous
  year

#### Scenario: The request holds a preset and explicit dates
- **WHEN** the request holds a preset together with explicit dates
- **THEN** the system uses the range of the preset
- **AND** without a preset, each absent side of the range falls back to the
  default window

#### Scenario: The range is inverted
- **WHEN** the start of the window is after its end
- **THEN** the system produces no period

### Requirement: Parent rows and child rows
The system SHALL group each category under its top-level segment. It SHALL show
each exact category as a child row. A parent row SHALL hold the sum of its
children. The system SHALL show a group as one row when the only member is the
name of the parent.

#### Scenario: A parent has two children
- **WHEN** `groceries-ah` and `groceries-lidl` have spend
- **THEN** a `groceries` parent row sums both, and each one appears as a child
  row

### Requirement: Uncategorized row
The system SHALL sum each transaction without an effective category into one
Uncategorized row. The system SHALL fold a null category and an empty category
together.

#### Scenario: The data holds null and empty categories
- **WHEN** some transactions have a null category, and others have an empty one
- **THEN** the system sums both into the single Uncategorized row

### Requirement: Row sorting
The system SHALL sort the top-level rows by the category label or by the total,
in ascending or descending order. The default is the category label in ascending
order. The child rows SHALL stay in alphabetic order, whatever the sort is.

#### Scenario: The user sorts by the descending total
- **WHEN** the user selects the descending total sort
- **THEN** the top-level row with the largest total comes first, and the child
  rows stay in alphabetic order

### Requirement: Shared filters
The trends SHALL accept the same filters as the transactions view. They are the
search, the category include list, the category exclude list, the tag, the
account, and the amount range. The subtree matching is identical.

#### Scenario: The user excludes a subtree
- **WHEN** the user excludes a parent category
- **THEN** neither the parent nor a descendant contributes to a cell

### Requirement: Exact sums behind each link
Each cell and each row label SHALL link to the transactions view. The link SHALL
carry the clamped date range of the period, the exact set of categories that the
cell summed, and the selected accounts. The link SHALL also carry the active
search, exclude-category, tag, and amount filters. The sum of the linked list
therefore equals the value on the screen.

#### Scenario: The user clicks a parent cell
- **WHEN** the user clicks the cell of a parent row
- **THEN** the link names each child category that the cell summed, and not the
  name of the parent alone

#### Scenario: The system clamps an edge period
- **WHEN** the first period is partly outside the window
- **THEN** its link carries the clamped start date, and it selects no
  transaction outside the window

#### Scenario: The user clicks a cell with the transfers included
- **WHEN** the user clicks a cell while the trends include the transfers
- **THEN** the link does not carry the include-transfers parameter, and the
  transactions view applies its own default

### Requirement: URL state and partial refresh
The query string SHALL hold the complete trends state. The system SHALL also
serve the table as a separate partial. The system SHALL render the complete page
if the user opens the partial URL directly.

#### Scenario: The user opens the partial URL directly
- **WHEN** the user opens the trends table URL without the partial-request
  header
- **THEN** the system renders the complete page
