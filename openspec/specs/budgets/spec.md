# Budgets Specification

## Purpose

This capability lets the user set a spending target for a category and a period.
The user can also maintain those targets across time.

## Requirements

### Requirement: Budget definition
A budget SHALL hold a category, an amount, and a period of `year`, `month`, or
`week`. It SHALL also hold an optional validity start date, an optional validity
end date, and optional notes. A validity start SHALL be the first day of a
period of that type. A validity end SHALL be the last day of a period of that
type. A budget with no validity end SHALL apply to each later period.

#### Scenario: The user creates a minimal budget
- **WHEN** the user creates a budget with only a category, an amount, and a
  period
- **THEN** the system stores the budget with no validity bounds
- **AND** the budget applies to each period of that type

#### Scenario: A monthly budget starts in November
- **WHEN** the user creates a monthly budget with the validity start 1 November
  and no validity end
- **THEN** the budget applies to November and to each later month

#### Scenario: The validity start is in the middle of a month
- **WHEN** the user creates a monthly budget with the validity start 15 November
- **THEN** the system rejects the request with status 400, and the message asks
  for the first day of a month

### Requirement: Validation of the budget form
A create or an update SHALL require a category, a valid period, and a numeric
amount. The system SHALL otherwise reject the request with status 400 and store
nothing. The system SHALL store the category in normalized form.

#### Scenario: The amount is not a number
- **WHEN** the amount is not a number
- **THEN** the system responds with status 400 and an invalid-amount message

#### Scenario: The category needs normalization
- **WHEN** the user enters the category ` Groceries `
- **THEN** the system stores `groceries`

### Requirement: Defaults on the add form
The add-budget form SHALL default its validity start to the first day of the
current period of the active tab. The form SHALL leave the validity end empty,
so that the budget repeats. The edit form SHALL keep both validity fields.

#### Scenario: The Monthly tab is active
- **WHEN** the Monthly tab is active
- **THEN** the add form proposes the first day of the current month as the
  start, and it proposes no end

#### Scenario: The user ends a budget
- **WHEN** the user edits a monthly budget and sets the validity end to the last
  day of December
- **THEN** the budget applies up to December and not after it

### Requirement: Edit and delete functions
The system SHALL provide an edit form for each budget. The system SHALL let the
user delete a budget. The system SHALL then return the user to the budgets page.

#### Scenario: The request names an unknown budget
- **WHEN** an edit, update, or delete request names a budget id that does not
  exist
- **THEN** the system responds with status 404

### Requirement: No overlap of budgets for one category and period
The system SHALL allow several budgets for one category and period when their
validity ranges do not overlap. An empty start SHALL mean no lower limit, and
an empty end SHALL mean no upper limit. The system SHALL reject a create or an
update that makes two ranges overlap. The message SHALL name the other budget.

#### Scenario: The user adds a budget after an ended budget
- **WHEN** a monthly `groceries` budget runs from July to October, and the user
  adds a monthly `groceries` budget from November
- **THEN** the system stores the second budget

#### Scenario: The user adds an overlapping budget
- **WHEN** a monthly `groceries` budget runs from July with no end, and the user
  adds a monthly `groceries` budget from November
- **THEN** the page shows an error that names the existing budget, and the
  system stores nothing

#### Scenario: The user edits a budget onto an overlap
- **WHEN** the user edits a budget so that its range overlaps another budget of
  the same category and period
- **THEN** the system rejects the request with status 400

### Requirement: Monthly and yearly tabs with a period selector
The budgets page SHALL show a Monthly tab and a Yearly tab. The default is
Monthly, and an unknown period SHALL fall back to Monthly. The Monthly tab SHALL
show a month selector, and the Yearly tab SHALL show a year selector. The URL
SHALL carry the tab and the selection. The default is the current month or
year. The table SHALL report the window of the selected month or year.

#### Scenario: The user opens the page with no period
- **WHEN** the user opens the budgets page with no period parameter
- **THEN** the Monthly tab is active, it selects the current month, and the page
  lists only the monthly budgets

#### Scenario: The user selects a past month
- **WHEN** the user selects August 2026 on the Monthly tab
- **THEN** the URL holds `month=2026-08`, and the table reports the window from
  1 August to 31 August 2026

#### Scenario: The user selects a past year
- **WHEN** the user selects 2025 on the Yearly tab
- **THEN** the URL holds `year=2025`, and the table reports the window of 2025

#### Scenario: The user gives a malformed month
- **WHEN** the month in the URL is not a valid year and month
- **THEN** the system responds with status 400

#### Scenario: An old link holds a reference date
- **WHEN** the URL holds `ref=2026-08-15` and no month
- **THEN** the Monthly tab selects August 2026

### Requirement: Sortable budget table
The user SHALL be able to sort the budget table on each column: the category,
the period, the window, the budget, the actual, the remainder, the percentage
in use, and the status. A click on a column header SHALL sort on that column,
and a second click SHALL reverse the order. The URL SHALL carry the sort. With
no sort in the URL, the table SHALL sort on the budget amount from the largest
to the smallest. Equal values SHALL keep the category order.

#### Scenario: The user opens the page with no sort
- **WHEN** the user opens the budgets page with no sort parameter
- **THEN** the table lists the largest budget first

#### Scenario: The user sorts on the actual spend
- **WHEN** the user clicks the Actual header
- **THEN** the table lists the smallest actual first, and the URL holds the sort

#### Scenario: The user clicks the same header again
- **WHEN** the user clicks the Actual header a second time
- **THEN** the table lists the largest actual first

#### Scenario: The URL holds an unknown sort
- **WHEN** the URL holds a sort value that the system does not know
- **THEN** the table uses the default sort
