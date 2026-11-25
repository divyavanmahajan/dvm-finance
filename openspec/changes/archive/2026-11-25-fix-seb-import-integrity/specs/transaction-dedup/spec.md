## MODIFIED Requirements

### Requirement: Deterministic transaction identity
The system SHALL derive the id of an imported transaction from its content. The
system SHALL join the account with the transaction identifier of the provider,
when one exists. The preferred order is the PayPal transaction id, the Wise
transaction id, the SEB voucher key, and then the First Tech FITID. The
system SHALL otherwise join the account, the transaction date, the amount, and
the first 16 hexadecimal characters of the MD5 hash of the description.

#### Scenario: The transaction has a provider identifier
- **WHEN** a PayPal transaction holds its own transaction id
- **THEN** the id is the account joined with that identifier, and it does not
  depend on the amount or the description

#### Scenario: The transaction has no provider identifier
- **WHEN** a bank transaction holds no provider identifier
- **THEN** the system derives its id from the account, the date, the amount, and
  the hash of the description

#### Scenario: The system parses the same file twice
- **WHEN** the system parses the same statement file twice
- **THEN** it produces the same ids both times

#### Scenario: Two downloads overlap
- **WHEN** two First Tech downloads cover the same transaction
- **THEN** both give the id `ftfcu:<last 4 digits>_<FITID>`, and the second
  import counts the transaction as a duplicate

#### Scenario: Two SEB card payments share one voucher number
- **WHEN** an SEB export holds two card payments with the voucher number
  `5400000001` on different days
- **THEN** the system gives them two different ids, and it stores both

### Requirement: The transaction id does not change
The system SHALL NOT derive the transaction id from the end-to-end reference.
The id of each already imported transaction SHALL stay the same after this
change. The manual categorization of each row therefore survives. The only
exception is an SEB transaction: the system SHALL change its id one time, as
the requirement "New id of a stored SEB transaction" tells.

#### Scenario: The user imports a known statement again
- **WHEN** the user imports a statement that the system imported before this
  change
- **THEN** the system reports each transaction as a duplicate, and it writes no
  second row

## ADDED Requirements

### Requirement: The SEB voucher key
The id of an SEB transaction SHALL be the account, the voucher number, the
booking date, the krona amount, and the krona balance, joined with `_`. The
system SHALL write the date as `YYYY-MM-DD`. It SHALL write each krona value
with exactly 2 decimal places, a period, and a leading `-` for a negative
value. It SHALL write an empty text for a missing balance. The desktop app and
the iOS app SHALL give the same id.

#### Scenario: A card payment
- **WHEN** an SEB row has the voucher number `5400000001`, the booking date
  2026-10-02, the amount `-632,900`, and the balance `8985,230`
- **THEN** the id is
  `seb:divyavanmahajan_5400000001_2026-10-02_-412.30_1234.56`

#### Scenario: Two equal payments on one day
- **WHEN** an SEB export holds two payments of -149.00 krona to one merchant on
  2026-10-19 with one voucher number, and the balances 3100.25 and 2200.75
- **THEN** the system gives them two different ids, because the balances are
  different

#### Scenario: The rate changes
- **WHEN** the system imports one SEB row two times with two different ECB
  rates
- **THEN** the id is the same both times, because the id holds the krona amount
  and not the euro amount

### Requirement: New id of a stored SEB transaction
A schema migration SHALL change the id of each stored SEB transaction to the
SEB voucher key. It SHALL take the voucher number, the krona amount, and the
krona balance from the structured description of the row, and the date from
the booking date. It SHALL change each reference to the old id in the same
step. It SHALL keep each other field of the row.

#### Scenario: The migration runs on a stored SEB row
- **WHEN** the database holds the row `seb:divyavanmahajan_5400000001` with the
  booking date 2026-10-02, the native amount -412.3, and the native balance
  1234.56
- **THEN** after the migration the row has the id
  `seb:divyavanmahajan_5400000001_2026-10-02_-412.30_1234.56`

#### Scenario: The row holds a manual category
- **WHEN** the migration changes the id of a row with a manual category and
  manual tags
- **THEN** the manual category and the manual tags stay the same

#### Scenario: The audit trail refers to the row
- **WHEN** a rule change item or a merged row refers to the old id
- **THEN** after the migration it refers to the new id

#### Scenario: The user imports the latest SEB file after the migration
- **WHEN** the database holds 89 SEB rows after the migration, and the user
  imports an SEB file with 182 transactions that includes those 89
- **THEN** the import adds 93 transactions and counts 89 as duplicates
