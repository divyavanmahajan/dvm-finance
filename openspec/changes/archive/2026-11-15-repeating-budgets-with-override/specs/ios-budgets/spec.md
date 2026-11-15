# Spec Delta

## ADDED Requirements

### Requirement: Several budgets for one category
The app SHALL store several budgets for one category and period, as the desktop
does. A database migration SHALL replace the unique index on the category and
the period with a plain index. A snapshot import SHALL match a budget by the
category, the period, and the validity start, and it SHALL treat an overlap in
the same way as the desktop. The report SHALL show the budget that is valid in
each window.

#### Scenario: The phone imports two budgets for one category
- **WHEN** the phone imports a snapshot with a monthly `groceries` budget from
  July to October and one from November with no end
- **THEN** the phone stores both budgets, and the November report shows the
  November budget

#### Scenario: The phone reports an earlier month
- **WHEN** the phone holds those two budgets and reports August
- **THEN** the report shows the budget from July to October
