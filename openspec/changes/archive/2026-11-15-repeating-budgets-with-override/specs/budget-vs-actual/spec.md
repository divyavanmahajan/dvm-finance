# Spec Delta

## MODIFIED Requirements

### Requirement: Seed of one budget for each top-level category
The system SHALL offer one action that creates budgets for the top-level
categories. The budget takes the period of the active tab, and the three-month
average as the amount. For a yearly budget, the amount is 12 times the monthly
average, to two decimal places. The action SHALL skip a category without recent
spend, and it SHALL skip the categories `income` and `transfer`. A seeded budget
SHALL have no validity end.

#### Scenario: The user seeds the monthly budgets
- **WHEN** the Monthly tab is active, three top-level categories have recent
  spend, and one of them already has a monthly budget for the selected month
- **THEN** the dialog selects the two other categories, and the system creates
  two budgets and leaves the existing one unchanged

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

#### Scenario: The data holds an income category
- **WHEN** the data holds the top-level categories `income` and `transfer` with
  recent amounts
- **THEN** the dialog does not list them, and the system creates no budget for
  them

#### Scenario: A seeded budget repeats
- **WHEN** the system seeds a monthly budget that starts in November
- **THEN** the budget has no validity end, and the page shows it in December

## ADDED Requirements

### Requirement: Dialog before the seed
The seed action SHALL be in the content of the Monthly tab and of the Yearly
tab, beside the period selector. It SHALL first show a dialog. On the Monthly
tab, the dialog SHALL ask for the start month. On the Yearly tab, it SHALL ask
for the start year. The month or year of the tab SHALL be the default. The URL
SHALL carry the selection. The dialog SHALL write nothing until the user
confirms.

#### Scenario: The user opens the dialog on the Monthly tab
- **WHEN** the user clicks the seed action on the Monthly tab in November 2026
- **THEN** the dialog asks for a month, and it proposes November 2026

#### Scenario: The user opens the dialog on the Yearly tab
- **WHEN** the user clicks the seed action on the Yearly tab in 2026
- **THEN** the dialog asks for a year, and it proposes 2026

#### Scenario: The tab shows a later month
- **WHEN** the Monthly tab shows March 2027, and the user clicks the seed action
- **THEN** the dialog proposes March 2027

#### Scenario: The user cancels the dialog
- **WHEN** the user closes the dialog without a confirmation
- **THEN** the system creates and changes no budget

### Requirement: Content of the seed dialog
For each top-level category with recent spend, the dialog SHALL show a checkbox,
the proposed amount, and the budget that is valid at the start of the selected
period. The user SHALL be able to edit the amount. The dialog SHALL select each
category with no valid budget. It SHALL clear each category with a valid
budget. The average SHALL use the three complete months before the current
month.

#### Scenario: A category has an expired budget
- **WHEN** a category has a monthly budget that ended in July, and the user
  selects November
- **THEN** the dialog shows no valid budget for the category, and it selects
  the category with the current average as the amount

#### Scenario: A category has a valid budget
- **WHEN** a category has a monthly budget of 400 from July with no end, and the
  user selects November
- **THEN** the dialog shows the budget of 400 from July, and it clears the
  checkbox of the category

#### Scenario: The user changes the month
- **WHEN** the user changes the month in the dialog
- **THEN** the dialog shows the valid budgets for the new month

### Requirement: Override from the selected period
When the user selects a category that has a valid budget, the system SHALL
override that budget from the start of the selected period. If the valid budget
starts on that day, the system SHALL change its amount. Otherwise the system
SHALL end the valid budget on the day before, and create a new budget from that
day. The new budget SHALL end on the day before the next later budget of the
category, if one exists.

#### Scenario: The user overrides a budget from November
- **WHEN** a monthly `groceries` budget of 400 runs from July with no end, and
  the user overrides it from November with 450
- **THEN** the old budget ends on 31 October, a new budget of 450 starts on
  1 November with no end, and the page shows 400 for August

#### Scenario: The valid budget starts in the selected month
- **WHEN** a monthly `groceries` budget starts on 1 November, and the user
  overrides it from November with 450
- **THEN** the system changes the amount of that budget to 450, and it creates
  no other budget

#### Scenario: A later budget exists
- **WHEN** a monthly `groceries` budget starts on 1 March next year, and the
  user creates a `groceries` budget from November
- **THEN** the new budget ends on the last day of February next year
