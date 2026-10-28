# Spec Delta

## Purpose

This capability lets the user record a cash payment on the phone, and remove it
again. It mirrors the manual transactions of the desktop application, so that
either device can hold the cash spending of the user. It is also the only
normative home for the exclusion of a flagged row on the phone.

## ADDED Requirements

### Requirement: Creation of a hand-entered transaction on the phone
The app SHALL let the user create one transaction in the fixed pseudo account
`CASH`. The app SHALL require a date, an amount, and a description, and it SHALL
accept an optional category and optional tags. The app SHALL refuse a form
without a date, without an amount, or with an amount of zero. This behavior is
identical to the desktop application.

#### Scenario: The user records a cash payment on the phone
- **WHEN** the user submits a date, an amount of -20.00, and a description
- **THEN** the app creates one transaction in the account `CASH`

#### Scenario: The form holds no amount
- **WHEN** the user submits the form without an amount
- **THEN** the app refuses the form, names the missing amount, and writes
  nothing

### Requirement: Parity of the identity and of the manual fields
The app SHALL give a hand-entered transaction a UUID as its id, and it SHALL
mark the row as hand-entered. The app SHALL store the typed category as a manual
category, and the typed tags as manual tags. The category pass on the phone
SHALL therefore skip the row, exactly as it skips a manually categorized
transaction.

#### Scenario: The user creates a row and then imports a file
- **WHEN** the user creates a hand-entered transaction, and the rules run after
  a later file import
- **THEN** the category of that transaction does not change

#### Scenario: Both devices create a cash row
- **WHEN** the phone and the computer each create a hand-entered transaction,
  and the user merges the two snapshots
- **THEN** both rows exist, because each row holds its own UUID

### Requirement: Edit of a hand-entered transaction on the phone
The app SHALL let the user change the date, the amount, the description, the
category, and the tags of a hand-entered transaction. The row SHALL keep its id.
The app SHALL stamp the row as updated, so that a delta export carries it. The
app SHALL refuse the edit of an imported transaction.

#### Scenario: The user corrects an amount on the phone
- **WHEN** the user changes the amount of a hand-entered transaction
- **THEN** the row keeps its id, and a delta export carries the new amount

#### Scenario: The user opens an imported transaction
- **WHEN** the user opens an imported transaction
- **THEN** the app offers the category and the tag functions only

### Requirement: The flag replaces the deletion on the phone
The app SHALL let the user flag a hand-entered transaction for removal, and SHALL
let the user remove that flag again. A flag SHALL record the time of the flag.
The app SHALL NOT delete the row. The app SHALL refuse a flag for an imported
transaction.

#### Scenario: The user flags a row on the phone
- **WHEN** the user flags a hand-entered transaction
- **THEN** the row stays in the local database, and it holds the time of the
  flag

#### Scenario: The flag reaches the computer
- **WHEN** the user flags a row on the phone and then exports a snapshot
- **THEN** the computer receives the row with its flag, and hides it

### Requirement: Default exclusion of a flagged transaction on the phone
Each list and each aggregation of the app SHALL exclude a flagged transaction.
This rule binds the transactions list, the category trends, and the budget
actuals. The rule is identical to the rule of the desktop application. Other iOS
capabilities inherit it, and they do not repeat it.

#### Scenario: The user opens the transactions tab
- **WHEN** the local database holds a flagged transaction
- **THEN** the rows and the totals hold no flagged transaction

#### Scenario: The app computes the trends or the budget actuals
- **WHEN** the app computes the trends or the budget actuals
- **THEN** a flagged transaction contributes nothing to a cell or a total

### Requirement: Two surfaces still read a flagged transaction on the phone
A snapshot export of the app SHALL hold a flagged transaction with its flag. A
snapshot import SHALL keep the flag of an incoming row. The duplicate check
SHALL treat the id of a flagged transaction as taken. No other surface of the
app SHALL read a flagged transaction.

#### Scenario: The user imports a snapshot with a flagged row
- **WHEN** the user imports a snapshot that holds a flagged transaction
- **THEN** the app stores the row with its flag, and the row appears in no list
  and in no total

#### Scenario: The user exports a snapshot from the phone
- **WHEN** the local database holds a flagged transaction
- **THEN** the exported file holds that transaction and the time of its flag

### Requirement: The purge on the phone
The app SHALL offer a purge that deletes each flagged transaction from the local
database. The purge SHALL copy the local database to a backup first. The purge
SHALL delete no other row, and it SHALL report the number of the deleted rows.
The app SHALL ask the user to confirm, because the app cannot undo the purge.

#### Scenario: The user purges a flagged row on the phone
- **WHEN** the local database holds one flagged row and the user confirms the
  purge
- **THEN** the app writes a backup, deletes exactly that row, and reports the
  number one

#### Scenario: A purged row returns from the computer
- **WHEN** the phone purges a row, and a later snapshot from the computer holds
  that row with its flag
- **THEN** the row returns flagged, and it stays out of each list and each total

### Requirement: No pseudo account editor on the phone
The app SHALL NOT create, rename, or remove a pseudo account. The account `CASH`
is fixed, and it is identical on both devices. The app SHALL NOT write a
hand-entered transaction to a bank account.

#### Scenario: The user opens the account filter on the phone
- **WHEN** the local database holds one hand-entered transaction
- **THEN** the account filter offers `CASH` beside each bank account, and it
  offers no function that changes the account
