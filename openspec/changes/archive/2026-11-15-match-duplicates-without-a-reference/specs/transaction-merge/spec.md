# Spec Delta

## ADDED Requirements

### Requirement: Discovery of a group with no reference
The system SHALL find a group of live rows that hold no usable end-to-end
reference, by the account, the transaction date, the amount, the counterparty
IBAN, and the remittance text. A transfer between two accounts of the user
carries no reference, so only this key finds its group.

#### Scenario: Two forms of a transfer with no reference
- **WHEN** one account holds two live rows of one transfer of -1000,00 euro,
  each from another statement file, and both hold the reference `NOTPROVIDED`
- **THEN** the system reports the two rows as one group

#### Scenario: The rows hold a usable reference
- **WHEN** two rows hold the same usable end-to-end reference
- **THEN** the system reports one group by the reference, and it does not report
  a second group for the same rows

### Requirement: Refusal of a group from one statement file
The system SHALL refuse a group of the second key when one statement file gives
more than one row of it. Such a group holds a genuine repeated payment. The
system SHALL report the refused group with that reason.

#### Scenario: One file gives two rows of the group
- **WHEN** a group of the second key holds two rows of one statement file
- **THEN** the system merges nothing, and the report names the group with the
  reason of the statement file

#### Scenario: Each file gives one row
- **WHEN** a group of the second key holds one row of each of two statement
  files
- **THEN** the system merges the group

### Requirement: The report names the key of a group
Each merged group and each refused group SHALL name the key that found it. The
value is the reference or the counterparty. The user can therefore see why the
system joined two rows.

#### Scenario: The reference found the group
- **WHEN** the system merges a group that the end-to-end reference found
- **THEN** the report names the reference as the key of that group

#### Scenario: The counterparty found the group
- **WHEN** the system merges a group that the second key found
- **THEN** the report names the counterparty IBAN and the remittance text as the
  key of that group
