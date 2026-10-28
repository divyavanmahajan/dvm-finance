# Spec Delta

## Purpose

This capability lets the user record a payment that no statement reports, for
example a cash payment. It holds the rules for the creation, the edit, the
removal, and the purge of a hand-entered transaction. It is also the only
normative home for the exclusion of a row that the user flagged for removal.

## ADDED Requirements

### Requirement: The fixed pseudo account
Each hand-entered transaction SHALL belong to one fixed pseudo account with the
reserved identifier `CASH`. The system SHALL NOT let a parser or a downloader
write a transaction to this account. A snapshot import SHALL write a row to this
account only when the row is hand-entered, because this is how the two devices
share the cash rows. The account SHALL appear beside the bank accounts in each
account filter and in each account list.

#### Scenario: The user opens the account filter
- **WHEN** the database holds one hand-entered transaction
- **THEN** the account filter offers `CASH` beside each bank account

#### Scenario: A statement names the reserved account
- **WHEN** an upload or a download holds a transaction for the account `CASH`
- **THEN** the system rejects that transaction and reports the reserved account

#### Scenario: A snapshot holds a hand-entered row
- **WHEN** a snapshot from the other device holds a hand-entered transaction for
  the account `CASH`
- **THEN** the merge writes the row, because a hand-entered row is the one kind
  of row that belongs to this account

### Requirement: Creation of a hand-entered transaction
The system SHALL offer a form that creates one transaction in the pseudo
account. The form SHALL require a date, an amount, and a description. The form
SHALL accept an optional category and optional tags. The system SHALL reject a
form without a date, without an amount, or with an amount of zero. The system
SHALL report the reason for each rejection, and it SHALL write nothing.

#### Scenario: The user records a cash payment
- **WHEN** the user submits a date, an amount of -20.00, and a description
- **THEN** the system creates one transaction in the account `CASH`

#### Scenario: The form holds no amount
- **WHEN** the user submits the form without an amount
- **THEN** the system rejects the form, names the missing amount, and writes
  nothing

### Requirement: The typed category is a manual category
The system SHALL store the category of a hand-entered transaction as a manual
category, and the tags as manual tags. A rule reapplication SHALL therefore
never replace them. A tag-only rule MAY still add a tag to a hand-entered
transaction, exactly as it does for an imported transaction.

#### Scenario: The user reapplies the rules
- **WHEN** the user reapplies each rule after the creation of a hand-entered
  transaction
- **THEN** the category of that transaction does not change

#### Scenario: A tag-only rule matches a hand-entered transaction
- **WHEN** a tag-only rule matches the description of a hand-entered transaction
- **THEN** the system adds the tag, and the category does not change

### Requirement: Edit of a hand-entered transaction
The system SHALL let the user change the date, the amount, the description, the
category, and the tags of a hand-entered transaction. The transaction SHALL keep
its id after each edit. The system SHALL record the time of the edit, so that a
delta snapshot holds the new values.

#### Scenario: The user corrects an amount
- **WHEN** the user changes the amount of a hand-entered transaction
- **THEN** the transaction keeps its id, and the next delta snapshot holds the
  new amount

#### Scenario: The user tries to edit an imported transaction
- **WHEN** the user requests the edit form for an imported transaction
- **THEN** the system refuses the request

### Requirement: A flag replaces the deletion
The system SHALL let the user flag a hand-entered transaction for removal, and
SHALL let the user remove that flag again. A flag SHALL record the time of the
flag. The system SHALL NOT delete the row. The system SHALL refuse a flag for an
imported transaction.

#### Scenario: The user flags a row
- **WHEN** the user flags a hand-entered transaction
- **THEN** the row stays in the database, and it holds the time of the flag

#### Scenario: The user restores a row
- **WHEN** the user removes the flag from a hand-entered transaction
- **THEN** the row appears again in the transactions list and in each total

#### Scenario: The user flags an imported transaction
- **WHEN** the user requests a flag for an imported transaction
- **THEN** the system refuses the request

### Requirement: Default exclusion of a flagged transaction
Each transaction list and each aggregation SHALL exclude a flagged transaction.
This rule binds seven surfaces. They are the transactions list, the category
trends, the cash flow, and the budget actuals. They are also the tag usage
counts, the match count of each rule, and the rule preview. Other capabilities
inherit this rule, and they do not repeat it.

#### Scenario: The user opens the default list
- **WHEN** the user opens the transactions list
- **THEN** the rows and the summary totals hold no flagged transaction

#### Scenario: The system computes an aggregation
- **WHEN** the system computes the trends, the cash flow, or the budget actuals
- **THEN** a flagged transaction contributes nothing to a cell or a total

#### Scenario: The system counts the use of a tag
- **WHEN** the system counts the transactions of a tag, the matches of a rule,
  or the rows of a rule preview
- **THEN** it counts no flagged transaction

### Requirement: Two surfaces still read a flagged transaction
A snapshot export SHALL hold a flagged transaction with its flag, so that the
flag reaches each other machine. The duplicate check SHALL treat the id of a
flagged transaction as taken, so that a second row cannot claim it. No other
surface SHALL read a flagged transaction.

#### Scenario: The system exports a snapshot
- **WHEN** the database holds a flagged transaction
- **THEN** the exported file holds that transaction and the time of its flag

#### Scenario: A purged row returns from another machine
- **WHEN** a machine purges a row, and a later snapshot from a second machine
  holds that row with its flag
- **THEN** the row returns flagged, and it stays out of each list and each total

### Requirement: The purge removes the flagged transactions
The system SHALL offer a purge that deletes each flagged transaction from the
database. The purge SHALL copy the database to a timestamped backup beside it
before it deletes a row. The purge SHALL delete no other row. The purge SHALL
report the number of the deleted rows. The purge SHALL ask the user to confirm,
because the app cannot undo it.

#### Scenario: The user purges two flagged rows
- **WHEN** the database holds two flagged rows and the user confirms the purge
- **THEN** the system writes a backup, deletes exactly those two rows, and
  reports the number two

#### Scenario: The database holds no flagged row
- **WHEN** the user runs the purge and the database holds no flagged row
- **THEN** the system deletes nothing and reports the number zero

### Requirement: The user sees how to fund the pseudo account
The create form SHALL tell the user to categorize as a transfer the withdrawal
that funds the pseudo account. The withdrawal otherwise counts as spending in
the bank account, and the hand-entered rows count the same money a second time.

#### Scenario: The user opens the create form
- **WHEN** the user opens the form for a hand-entered transaction
- **THEN** the form explains that the funding withdrawal belongs in a transfer
  category
