# iOS Category Trends Specification

## Purpose

The trends tab shows the spend for each category across time on the phone. Each
cell opens the transactions behind its value.

## Requirements

### Requirement: Matrix of category against period
The trends tab SHALL show a scrollable matrix of the effective category against
the period. The app SHALL roll each category up to its top-level segment. The
app SHALL let the user expand a group into its exact child categories. The
default window is the last 12 months.

#### Scenario: The user opens the trends tab
- **WHEN** the user opens the trends tab
- **THEN** the app shows the last 12 months

#### Scenario: The user expands a group
- **WHEN** the user expands a rolled-up category row
- **THEN** the app lists the exact child categories with their own values

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
