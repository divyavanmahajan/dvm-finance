## Purpose

Lets the user of the iOS app delete all data in the app and start again with
an empty database, after an explicit confirmation.

## ADDED Requirements

### Requirement: Delete all data control
The import tab SHALL hold a "Delete all data" control as its last section. The
control SHALL use the destructive role, a red color, and a warning icon.

#### Scenario: The user opens the import tab
- **WHEN** the user opens the import tab and scrolls to the end
- **THEN** the last section holds a red "Delete all data" button with a warning
  icon

### Requirement: Confirmation before the deletion
Before the deletion, the app SHALL show a confirmation prompt. The prompt SHALL
warn that the deletion removes each transaction, rule, tag, budget, and history
record, and that the user cannot undo it. The prompt SHALL tell the user to
export a snapshot first to keep a copy. The prompt SHALL hold a destructive
"Delete all data" action and a "Cancel" action.

#### Scenario: The user cancels
- **WHEN** the user taps "Delete all data" and then taps "Cancel"
- **THEN** the app deletes nothing

#### Scenario: The user confirms
- **WHEN** the user taps "Delete all data" and then confirms the deletion
- **THEN** the app deletes all data and shows a message with the count of the
  deleted transactions

### Requirement: Scope of the deletion
The deletion SHALL delete each row of each data table in one database
transaction. The data tables are the transactions, the rules and their
conditions, the budgets, the change reports, the snapshot imports, the merge
reports, and the export state. The deletion SHALL also delete the exported
snapshot files and the database backups that a snapshot import made. The deletion SHALL keep the database schema and the
machine identity of the app.

#### Scenario: The deletion ends
- **WHEN** the deletion ends
- **THEN** each tab shows an empty state, and the transactions tab shows the
  offer to load the sample data

#### Scenario: A snapshot import made a backup
- **WHEN** an earlier snapshot import wrote a database backup, and the user
  deletes all data
- **THEN** the app deletes the backup file, and the live database stays

#### Scenario: The deletion fails
- **WHEN** an error stops the deletion
- **THEN** the app keeps all data, because the database transaction rolls back,
  and the app shows the error

#### Scenario: The user exports after the deletion
- **WHEN** the user imports a snapshot after the deletion
- **THEN** the import works as on a new installation
