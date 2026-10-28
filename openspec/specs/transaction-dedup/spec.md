# Transaction Deduplication Specification

## Purpose

Each transaction has a deterministic identity. The user can therefore import the
same statement twice, download overlapping date ranges, and merge a snapshot
across machines without a heuristic.

## Requirements

### Requirement: Deterministic transaction identity
The system SHALL derive the id of a transaction from its content. The system
SHALL join the account with the transaction identifier of the provider, when one
exists. The preferred order is the PayPal transaction id, the Wise transaction
id, and then the SEB voucher number. The system SHALL otherwise join the
account, the transaction date, the amount, and the first 16 hexadecimal
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
