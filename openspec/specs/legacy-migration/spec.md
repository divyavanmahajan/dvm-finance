# Legacy Migration Specification

## Purpose

This capability moves an existing dataset from the predecessor application into
this application. It runs once, and it never puts the source file at risk.

## Requirements

### Requirement: One-time migration command
The system SHALL provide a command that takes the path to a legacy database. The
command SHALL copy the transactions, the categorization rules, the rule
conditions, and the budgets into the database of this application.

#### Scenario: The user runs the migration
- **WHEN** the user runs the migration against a legacy database
- **THEN** the command copies those four tables
- **AND** the command prints the count of inserted and skipped rows for each
  table, and the path of the destination database

### Requirement: Read-only access to the legacy file
The command SHALL open the legacy database in read-only mode. A migration SHALL
NOT modify the source file.

#### Scenario: The migration ends
- **WHEN** a migration ends, with success or with failure
- **THEN** the legacy file is unchanged

### Requirement: Clear failure for an unreadable source
The command SHALL fail with a clear message and a non-zero exit status if the
legacy file is absent or unreadable.

#### Scenario: The file is absent
- **WHEN** the named legacy database does not exist
- **THEN** the command reports the problem and exits with a non-zero status

### Requirement: Schema validation
The command SHALL refuse to run if the legacy database has no expected table or
no expected column. The command SHALL NOT import partial data.

#### Scenario: An unknown schema variant
- **WHEN** the legacy database has no expected column
- **THEN** the command refuses, names the problem, and writes nothing

### Requirement: Tables that the migration skips
The command SHALL NOT copy the user table, the authentication table, or the
bookkeeping table of the legacy migration tool.

#### Scenario: The legacy database contains a user table
- **WHEN** the legacy database contains a user table
- **THEN** the command ignores that table

### Requirement: All-or-nothing write
The command SHALL run the complete migration as one transaction on the
destination database. A failure SHALL leave nothing written.

#### Scenario: An error occurs part way through
- **WHEN** an error occurs part way through the copy
- **THEN** the destination database holds no row from that run

### Requirement: Idempotent re-runs
A second run SHALL skip each row whose id already exists. The command SHALL
count those rows as skipped. It SHALL NOT fail, and it SHALL NOT create a
duplicate.

#### Scenario: The user runs the same migration twice
- **WHEN** the user runs the same migration twice
- **THEN** the second run inserts nothing and reports each row as skipped

### Requirement: UUIDs for the legacy rules
A legacy rule has no UUID. The command SHALL give each migrated rule a new
UUID, so that the rule can take part in a snapshot merge.

#### Scenario: The command migrates the rules
- **WHEN** the command migrates the legacy rules
- **THEN** each migrated rule has a UUID

### Requirement: Data directory selection
The command SHALL accept the data-directory option before the subcommand and
after it. The command SHALL fail with a clear message if the data directory is
not writable.

#### Scenario: The user gives the option after the subcommand
- **WHEN** the user gives the data directory after the subcommand
- **THEN** the command honours that value, and it does not override a value from
  before the subcommand
