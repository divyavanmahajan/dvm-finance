## MODIFIED Requirements

### Requirement: Transaction list
The transactions tab SHALL list the transactions in groups by date. Each row
SHALL show the effective category and the effective tags. The app SHALL show
each category name and each tag name in full. A long name SHALL wrap onto a
second line, and the chips SHALL flow onto a new line when the row is too
narrow. The app SHALL let the user search by text.

#### Scenario: The app shows the list
- **WHEN** the app shows the list
- **THEN** the transactions appear in groups under their dates

#### Scenario: The user types a search term
- **WHEN** the user types a search term
- **THEN** the list narrows to the transactions that match it

#### Scenario: A category name is long
- **WHEN** a row shows a category such as "education-tuition-chelseaballet"
  that does not fit on one line
- **THEN** the chip wraps the name onto a second line, and the row shows the
  full name without an ellipsis

#### Scenario: A row has several tags
- **WHEN** the category chip and the tag chips do not fit on one line
- **THEN** the chips flow onto the next line, and each chip shows its full name

### Requirement: Sample data for a new user
The app SHALL offer a fictional sample dataset, so that a new user can try each
screen before the user imports real data. The sample dataset SHALL hold one year
of transactions and a small set of monthly and yearly budgets.

The load SHALL add rows and SHALL NOT change or delete a row of the user. The
load SHALL skip a sample budget when the user has a budget with the same
category and period. A second load SHALL add nothing.

The removal SHALL delete each sample transaction and each sample budget, and
SHALL NOT delete another row.

#### Scenario: The database is empty
- **WHEN** the database holds no live transaction and the user opens the
  transaction list
- **THEN** the list shows an offer to load the sample data, and it tells the
  user how to import real data

#### Scenario: The empty-state button is legible
- **WHEN** the transaction list shows the offer to load the sample data
- **THEN** the "Load sample data" button shows its icon and its label, at the
  normal height of a button

#### Scenario: The user loads the sample data
- **WHEN** the user taps "Load sample data"
- **THEN** the app adds the sample transactions and budgets, and each screen
  shows them

#### Scenario: The user removes the sample data
- **WHEN** the user taps "Remove sample data" in the help tab or in the import
  tab
- **THEN** the app deletes only the sample rows, and the rows of the user stay
