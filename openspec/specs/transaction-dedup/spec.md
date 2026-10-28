# Transaction Deduplication Specification

## Purpose

Each transaction has a deterministic identity. The user can therefore import the
same statement twice, download overlapping date ranges, and merge a snapshot
across machines without a heuristic.

## Requirements

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

### Requirement: Duplicate detection
The system SHALL split an incoming batch into the new and the duplicate
transactions. A transaction is a duplicate when the database already holds its
id, or when an earlier transaction in the same batch already claimed that id.
The system SHALL keep the first appearance inside a batch.

#### Scenario: One file lists a transaction twice
- **WHEN** a statement lists the same transaction twice
- **THEN** the system keeps the first one and counts the second one as a
  duplicate

#### Scenario: A download covers known dates
- **WHEN** a download covers dates that the system already imported
- **THEN** the system reports the known transactions as duplicates, and it
  counts nothing twice

### Requirement: Idempotent insertion
The system SHALL write each transaction by its id, in a manner that makes a
second write of an existing id harmless. The system SHALL return the written
ids, so that the caller can categorize exactly that set.

#### Scenario: The system writes an existing id again
- **WHEN** the system inserts a transaction with an existing id
- **THEN** the operation succeeds, and it creates no second row

### Requirement: Normalization at insertion
An insertion SHALL normalize the category field and the manual category field.
An insertion SHALL default the currency to the euro, if the source states none.

#### Scenario: The source states no currency
- **WHEN** a parsed transaction holds no currency
- **THEN** the system stores the euro

### Requirement: Stored content hash
An insertion SHALL store a content hash for each transaction. The system SHALL
compute the hash from the normalized account, the date, the description, and the
amount with two decimal places. The hash is a second aid for duplicate
detection.

#### Scenario: The system inserts a transaction
- **WHEN** the system inserts a transaction
- **THEN** it stores the content hash beside the transaction

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
