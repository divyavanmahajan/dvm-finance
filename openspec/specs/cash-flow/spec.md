# Cash Flow Specification

## Purpose

The cash-flow report shows the income against the expense for each period, with
a net line. The user can see whether money came in faster than it went out.

## Requirements

### Requirement: Income, expense, and net for each period
For each period in the window, the system SHALL report the sum of the positive
amounts as the income. It SHALL report the sum of the absolute value of the
negative amounts as the expense. It SHALL report the income minus the expense as
the net. It SHALL also report the overall total of all three values.

#### Scenario: One period with two transactions
- **WHEN** a month contains a salary of +2000 and a purchase of -500
- **THEN** that month reports an income of 2000, an expense of 500, and a net of
  1500

#### Scenario: A period with no transaction
- **WHEN** a period inside the window has no transaction
- **THEN** that period reports zero income, zero expense, and zero net
- **AND** the report does not omit the period

### Requirement: Period breakdowns
The system SHALL support a breakdown by month, by week that starts on Monday,
or by year. The default is the month. The system SHALL fall back to the month
for an unknown breakdown.

#### Scenario: The user selects the weekly breakdown
- **WHEN** the user selects the weekly breakdown
- **THEN** each column covers one week from Monday to Sunday
- **AND** the system clamps the first column and the last column to the window

#### Scenario: The breakdown parameter is unknown
- **WHEN** the breakdown parameter is not month, week, or year
- **THEN** the system uses the monthly breakdown

### Requirement: Window selection
The user SHALL set the window as an explicit date range or as one of the named
presets. The preset takes priority. If the user gives neither, the window
defaults to the current calendar year.

#### Scenario: The user opens the page with no date
- **WHEN** the user opens the cash-flow page with no date parameter
- **THEN** the window runs from 1 January to 31 December of the current year

#### Scenario: The user gives a preset and explicit dates
- **WHEN** the user gives a preset together with explicit dates
- **THEN** the system uses the range of the preset

### Requirement: Account filter
The system SHALL accept a restriction to one account or more. The report SHALL
cover each account if the user names none.

#### Scenario: The user selects one account
- **WHEN** the user selects one account
- **THEN** only the transactions of that account contribute

### Requirement: Links from each period into the transactions view
Each period figure and the overall total SHALL link to the transactions view.
The link SHALL carry the period window and the selected accounts. The filter
model has no sign filter. An income figure and an expense figure therefore link
to each transaction of the period.

#### Scenario: The user clicks an income figure
- **WHEN** the user clicks the income figure of a period
- **THEN** the transactions view opens with that period and those accounts
- **AND** the list contains both the income and the expenses

### Requirement: URL state and partial refresh
The query string SHALL hold the complete cash-flow state. The system SHALL also
serve the table as a separate partial, so that a change to a control replaces
only the table.

#### Scenario: The user reopens a configured URL
- **WHEN** the user reopens a configured cash-flow URL
- **THEN** the same window, breakdown, accounts, and transfer setting apply
