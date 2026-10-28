# Spec Delta

## MODIFIED Requirements

### Requirement: Deterministic transaction identity
The system SHALL derive the id of an imported transaction from its content. The
system SHALL join the account with the transaction identifier of the provider,
when one exists. The preferred order is the PayPal transaction id, the Wise
transaction id, and then the SEB voucher number. The system SHALL otherwise join
the account, the transaction date, the amount, and the first 16 hexadecimal
characters of the MD5 hash of the description.

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

## ADDED Requirements

### Requirement: The id of a hand-entered transaction is a UUID
The system SHALL give a hand-entered transaction a UUID as its id. The id SHALL
NOT come from the content of the transaction. The id SHALL stay the same after
each edit of the date, the amount, or the description. The system SHALL mark the
row as hand-entered, so that each reader can tell the two kinds of id apart.

#### Scenario: The user creates a hand-entered transaction
- **WHEN** the user creates a hand-entered transaction
- **THEN** the id of the row is a UUID, and it holds no part of the amount or of
  the description

#### Scenario: The user edits a hand-entered transaction
- **WHEN** the user changes the amount of a hand-entered transaction
- **THEN** the id of the row does not change, and the system creates no second
  row

#### Scenario: Two hand-entered transactions hold the same values
- **WHEN** the user creates two hand-entered transactions with the same date,
  the same amount, and the same description
- **THEN** the system keeps both rows, because each row holds its own id

### Requirement: An import never matches a hand-entered transaction
The duplicate check SHALL NOT match an imported transaction against a
hand-entered transaction. The two kinds of id come from different rules, so a
collision between them is impossible. An imported transaction therefore always
enters the database, even when a hand-entered row records the same payment.

#### Scenario: A statement reports a payment that the user typed by hand
- **WHEN** the user records a payment by hand, and a later statement reports the
  same payment
- **THEN** the system imports the statement row as new, and it keeps the
  hand-entered row

### Requirement: The content hash of a hand-entered transaction
The system SHALL store a content hash for a hand-entered transaction, from the
same components as for an imported transaction. The system SHALL compute the
hash again after each edit, so that the hash always describes the stored values.

#### Scenario: The user edits a hand-entered transaction
- **WHEN** the user changes the description of a hand-entered transaction
- **THEN** the stored content hash matches the new description
