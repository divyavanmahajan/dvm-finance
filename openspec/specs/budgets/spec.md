# Budgets Specification

## Purpose

This capability lets the user set a spending target for a category and a period.
The user can also maintain those targets across time.

## Requirements

### Requirement: Budget definition
A budget SHALL hold a category, an amount, and a period of `year`, `month`, or
`week`. It SHALL also hold an optional validity start date, an optional validity
end date, and optional notes.

#### Scenario: The user creates a minimal budget
- **WHEN** the user creates a budget with only a category, an amount, and a
  period
- **THEN** the system stores the budget with no validity bounds
- **AND** the budget applies to each period of that type

### Requirement: One budget for each category and period
The system SHALL allow at most one budget for a combination of a category and a
period. The system SHALL reject a create or an update that duplicates one.

#### Scenario: The user creates a duplicate
- **WHEN** a monthly budget for `groceries` exists, and the user creates another
- **THEN** the page shows an error that names the existing budget, and the
  system stores nothing

#### Scenario: The user edits a budget onto an occupied combination
- **WHEN** the user edits a budget onto a category and a period that another
  budget occupies
- **THEN** the system rejects the request with status 400

### Requirement: Monthly and yearly tabs
The budgets page SHALL show a Monthly tab and a Yearly tab. The default is
Monthly. The URL SHALL carry the active tab. The system SHALL fall back to
Monthly for an unknown period. The URL SHALL also carry the reference date, and
the default reference date is today.

#### Scenario: The user opens the page with no period
- **WHEN** the user opens the budgets page with no period parameter
- **THEN** the Monthly tab is active, and the page lists only the monthly
  budgets

#### Scenario: The user gives a past reference date
- **WHEN** the user gives a reference date in a past month
- **THEN** the table reports the window of that month

#### Scenario: The user gives a malformed reference date
- **WHEN** the reference date is not a valid ISO date
- **THEN** the system responds with status 400

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
The add-budget form SHALL default its validity window to the current period
window of the active tab.

#### Scenario: The Monthly tab is active
- **WHEN** the Monthly tab is active
- **THEN** the add form proposes the first day and the last day of the current
  month

### Requirement: Edit and delete functions
The system SHALL provide an edit form for each budget. The system SHALL let the
user delete a budget. The system SHALL then return the user to the budgets page.

#### Scenario: The request names an unknown budget
- **WHEN** an edit, update, or delete request names a budget id that does not
  exist
- **THEN** the system responds with status 404
