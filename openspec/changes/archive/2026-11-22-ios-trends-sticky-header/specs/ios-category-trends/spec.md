## ADDED Requirements

### Requirement: The header row stays visible
The header row of the matrix SHALL stay at the top of the matrix while the
user scrolls the rows vertically. The header row holds the "Category" header,
the month headers, and the "Total" header. Each month header SHALL stay above
its value column during a horizontal scroll. The "Category" header SHALL keep
the width of the category column and its tap action.

#### Scenario: The user scrolls the rows down
- **WHEN** the matrix has more rows than the screen shows, and the user scrolls
  the rows down
- **THEN** the header row stays at the top of the matrix, and the rows scroll
  below it

#### Scenario: The user scrolls the months to the right
- **WHEN** the user scrolls the value columns to the right
- **THEN** each month header moves with its value column, and stays above it

#### Scenario: The category column changes its width
- **WHEN** the category column becomes narrow or wide
- **THEN** the "Category" header changes its width with the column, and the
  month headers stay above their value columns

#### Scenario: The user taps the pinned header
- **WHEN** the user scrolls the rows down and then taps the "Category" header
- **THEN** the category column stays wide, as it does when the rows are at the
  top
