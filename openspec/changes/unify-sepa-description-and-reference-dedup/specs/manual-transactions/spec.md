# Spec Delta

## MODIFIED Requirements

### Requirement: The purge removes the flagged transactions
The system SHALL offer a purge that deletes each flagged transaction from the
database. The purge SHALL NOT delete a merged row. A merged row holds a value in
`merged_into`, and the merge wrote its flag, not the user. The purge SHALL copy
the database to a timestamped backup beside it before it deletes a row. The
purge SHALL delete no other row. The purge SHALL report the number of the
deleted rows. The purge SHALL ask the user to confirm, because the app cannot
undo it.

#### Scenario: The user purges two flagged rows
- **WHEN** the database holds two flagged rows and the user confirms the purge
- **THEN** the system writes a backup, deletes exactly those two rows, and
  reports the number two

#### Scenario: The database holds no flagged row
- **WHEN** the user runs the purge and the database holds no flagged row
- **THEN** the system deletes nothing and reports the number zero

#### Scenario: The database holds a merged row
- **WHEN** the database holds one row that the user flagged and one row that a
  merge flagged, and the user confirms the purge
- **THEN** the system deletes the row of the user, keeps the merged row, and
  reports the number one

### Requirement: A flag replaces the deletion
The system SHALL let the user flag a hand-entered transaction for removal, and
SHALL let the user remove that flag again. A flag SHALL record the time of the
flag. The system SHALL NOT delete the row. The system SHALL refuse a flag for an
imported transaction. The list of the flagged transactions SHALL show only a row
that the user flagged. It SHALL NOT show a merged row.

#### Scenario: The user flags a row
- **WHEN** the user flags a hand-entered transaction
- **THEN** the row stays in the database, and it holds the time of the flag

#### Scenario: The user restores a row
- **WHEN** the user removes the flag from a hand-entered transaction
- **THEN** the row appears again in the transactions list and in each total

#### Scenario: The user flags an imported transaction
- **WHEN** the user requests a flag for an imported transaction
- **THEN** the system refuses the request

#### Scenario: The merge flagged an imported row
- **WHEN** a merge flagged an imported row, and the user opens the list of the
  flagged transactions
- **THEN** the list does not hold that row, so the user cannot restore it there

### Requirement: Two surfaces still read a flagged transaction
A snapshot export SHALL hold a flagged transaction with its flag, so that the
flag reaches each other machine. A snapshot export SHALL also hold the value of
`merged_into`, so that a merge reaches each other machine. The duplicate check
SHALL treat the id of a flagged transaction as taken, so that a second row
cannot claim it. No other surface SHALL read a flagged transaction.

#### Scenario: The system exports a snapshot
- **WHEN** the database holds a flagged transaction
- **THEN** the exported file holds that transaction and the time of its flag

#### Scenario: A purged row returns from another machine
- **WHEN** a machine purges a row, and a later snapshot from a second machine
  holds that row with its flag
- **THEN** the row returns flagged, and it stays out of each list and each total

#### Scenario: A merge reaches a second machine
- **WHEN** a machine merges a group, and it then shares a snapshot
- **THEN** the second machine holds the same survivor and the same merged row
