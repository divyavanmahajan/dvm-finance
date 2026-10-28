# iOS Budgets Specification

## Purpose

The budgets tab lets the user review and maintain the budget targets on the
phone. Each target shows the actual spend of its current period.

## Requirements

### Requirement: Monthly and yearly tabs
The budgets tab SHALL offer a Monthly selector and a Yearly selector. The
default is Monthly. The app SHALL report the budgets of the selected period.

#### Scenario: The user selects Yearly
- **WHEN** the user selects Yearly
- **THEN** the app reloads the report with the yearly budgets, and the add form
  defaults to the yearly period

### Requirement: Budget and actual in each row
Each row SHALL show the budget amount, the actual spend, the remaining amount,
the percentage in use, a status, and the period window.

#### Scenario: A budget has spend against it
- **WHEN** a budget has spend against it
- **THEN** its row shows the budget, the actual, the remainder, the percentage,
  and the status

### Requirement: Parity with the desktop computation
The app SHALL sum the absolute amounts of the transactions in the current period
window of the budget. It SHALL use the effective category of each transaction
and subtree matching. It SHALL exclude the transfers.

#### Scenario: Spend on a child category
- **WHEN** a budget covers a parent category, and spend exists on a child
  category
- **THEN** that spend counts against the budget

### Requirement: Add, edit, and delete functions
The app SHALL let the user create, edit, and delete a budget.

#### Scenario: The user deletes a budget
- **WHEN** the user deletes a budget
- **THEN** the budget disappears from the report

### Requirement: Seed from the recent average
The app SHALL offer an action that creates one budget for each top-level
category of the selected period. The action SHALL use the recent average as the
amount. It SHALL report what it created. It SHALL skip a category that already
has a budget.

#### Scenario: Each category already has a budget
- **WHEN** each top-level category already has a budget of that period
- **THEN** the action reports that it created no budget

#### Scenario: The user seeds from an empty state
- **WHEN** no budget exists, and the categories have recent spend
- **THEN** the empty state offers both an add action and a seed action

### Requirement: Explanation of the computation
The screen SHALL state how it computes the actuals. The statement SHALL include
the exclusion of the transfers.

#### Scenario: The app shows the budget report
- **WHEN** the app shows the budget report
- **THEN** a note explains the effective-category basis and the exclusion of the
  transfers
