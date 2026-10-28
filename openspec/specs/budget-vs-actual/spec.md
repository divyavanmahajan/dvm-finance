# Budget vs Actual Specification

## Purpose

This capability reports the real spend against each budget for its current
period. It also proposes a realistic amount from the recent spend, so that the
user does not have to guess.

## Requirements

### Requirement: Actual spend for a budget
The system SHALL sum the absolute amounts of the transactions inside the period
window. It SHALL include a transaction whose effective category is the category
of the budget or a descendant of that category.

#### Scenario: The spend is on a child category
- **WHEN** a budget covers `groceries`, and spend exists on `groceries-ah`
- **THEN** that spend counts against the budget

#### Scenario: The window holds a refund and a purchase
- **WHEN** a refund of +20 and a purchase of -100 fall inside the window
- **THEN** the actual is 120

### Requirement: Period windows
The period of a budget selects the type of its window. The system SHALL take
the window as the inclusive calendar year, the calendar month, or the week that
holds the reference date. A week runs from Monday to Sunday.

#### Scenario: The reference date is in February
- **WHEN** the reference date is 15 February
- **THEN** the window runs from 1 February to the last day of February

#### Scenario: The reference date is a Thursday
- **WHEN** the reference date is a Thursday
- **THEN** the window runs from the Monday of that week to its Sunday

### Requirement: Validity filter
The system SHALL omit a budget from the report when its validity window does not
overlap the reported period window.

#### Scenario: The budget is not yet active
- **WHEN** the validity of a budget starts after the end of the reported window
- **THEN** the report omits the budget

#### Scenario: The budget has expired
- **WHEN** the validity of a budget ended before the start of the reported
  window
- **THEN** the report omits the budget

### Requirement: Reported figures and status
For each reported budget, the system SHALL show the amount, the actual, the
remainder, the percentage in use, and the period window. The status is `over`
when the actual is more than the amount. It is `near` when the actual reaches 80
percent or more of a positive amount. It is `under` in each other case.

#### Scenario: The actual is near the limit
- **WHEN** the actual is 85 against a budget of 100
- **THEN** the status is `near`, and the percentage shows 85.0

#### Scenario: The actual is over the limit
- **WHEN** the actual is 120 against a budget of 100
- **THEN** the status is `over`, and the remainder is -20

#### Scenario: The budget amount is zero
- **WHEN** the amount of a budget is zero, and some spend exists
- **THEN** the percentage shows 0.0, and the status is `over`

### Requirement: Link from each category cell
The category of each reported budget SHALL link to the transactions view. The
link SHALL carry that category and the reported period window.

#### Scenario: The user clicks a budget row
- **WHEN** the user clicks the category of a budget
- **THEN** the transactions view opens with that category and that window

### Requirement: Hint from the recent average
While the user enters an amount, the system SHALL offer the average monthly
actual spend for the typed category. The average covers the last three complete
calendar months, and it excludes the month in progress. The system SHALL say so
when the category has no recent spend.

#### Scenario: The category has recent spend
- **WHEN** the user types a category with recent spend
- **THEN** the system shows the average monthly amount across the last three
  complete months

#### Scenario: The category has no recent spend
- **WHEN** the typed category has no spend in those months
- **THEN** the system shows a note about the absent spend, and not a number

#### Scenario: The user has typed no category
- **WHEN** the user has typed no category yet
- **THEN** the system shows no hint

### Requirement: Seed of one budget for each top-level category
The system SHALL offer one action that creates a budget for each top-level
category without one. The budget takes the period of the active tab, and the
three-month average as the amount. For a yearly budget, the amount is 12 times
the monthly average, to two decimal places. The action SHALL skip a category
without recent spend, and it SHALL never modify an existing budget.

#### Scenario: The user seeds the monthly budgets
- **WHEN** the Monthly tab is active, three top-level categories have recent
  spend, and one of them already has a monthly budget
- **THEN** the system creates two budgets and leaves the existing one unchanged

#### Scenario: The user seeds a yearly budget
- **WHEN** the Yearly tab is active, and the monthly average of a category is
  150
- **THEN** the amount of the seeded yearly budget is 1800.00

#### Scenario: A category has no recent spend
- **WHEN** the three-month average of a top-level category is zero
- **THEN** the system creates no budget for that category

#### Scenario: The system seeds a budget
- **WHEN** the system seeds a budget
- **THEN** its notes record the three-month average as the source, and they note
  the multiplication by 12 where it applies
