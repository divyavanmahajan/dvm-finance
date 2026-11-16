# Spec Delta

## MODIFIED Requirements

### Requirement: Deterministic transaction identity
The system SHALL derive the id of an imported transaction from its content. The
system SHALL join the account with the transaction identifier of the provider,
when one exists. The preferred order is the PayPal transaction id, the Wise
transaction id, the SEB voucher number, and then the First Tech FITID. The
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
