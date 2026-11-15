# Spec Delta

## MODIFIED Requirements

### Requirement: Duplicate detection
The system SHALL split an incoming batch into the new and the duplicate
transactions. A transaction is a duplicate when the database already holds its
id, or when an earlier transaction in the same batch already claimed that id. A
transaction is also a duplicate when it matches a stored end-to-end reference of
the same account. The system SHALL keep the first appearance inside a batch.

#### Scenario: One file lists a transaction twice
- **WHEN** a statement lists the same transaction twice
- **THEN** the system keeps the first one and counts the second one as a
  duplicate

#### Scenario: A download covers known dates
- **WHEN** a download covers dates that the system already imported
- **THEN** the system reports the known transactions as duplicates, and it
  counts nothing twice

#### Scenario: Two description forms report one payment
- **WHEN** one statement reports a SEPA payment in the tagged form, and a second
  statement reports the same payment of the same account in the labelled form
- **THEN** the system counts the second one as a duplicate, and it writes no
  second row

## ADDED Requirements

### Requirement: Stored end-to-end reference
The system SHALL store the end-to-end reference of a transaction in its own
indexed field. The value comes from the structured description. The system SHALL
store no value when the structured description holds none.

#### Scenario: The structured description holds the reference
- **WHEN** the system inserts a SEPA transaction with the end-to-end reference
  `KFF5Q4D85TQK39G6`
- **THEN** the row holds that value in the end-to-end reference field

#### Scenario: The description holds no reference
- **WHEN** the system inserts a point-of-sale transaction
- **THEN** the end-to-end reference field of the row is empty

### Requirement: Duplicate detection by the end-to-end reference
The duplicate check SHALL compare the account, the end-to-end reference, and the
amount. Two transactions of one account with the same reference and the same
amount are the same payment. The check SHALL apply inside a batch and against
the database.

#### Scenario: The reference matches a stored row
- **WHEN** an incoming transaction holds an end-to-end reference and an amount
  that a row of the same account already holds
- **THEN** the system counts the incoming transaction as a duplicate

#### Scenario: Two accounts hold the same reference
- **WHEN** two transactions of two different accounts hold the same end-to-end
  reference
- **THEN** the system counts neither one as a duplicate

### Requirement: A reversal is not a duplicate
The duplicate check SHALL NOT join a payment with its reversal. A reversal
carries the end-to-end reference of the payment that it reverses, with the
opposite sign. The amount belongs to the match key for this reason. The two
description forms of one payment always report the same amount, because they
describe one statement line.

#### Scenario: A direct debit and its reversal
- **WHEN** a direct debit of -149,88 and a `SEPA INCASSO TERUGBOEKING` of
  +149,88 hold the same end-to-end reference
- **THEN** the system counts neither one as a duplicate, and it writes both
  rows

#### Scenario: The two description forms of one payment
- **WHEN** the two description forms of one payment report the same amount
- **THEN** the system counts the second form as a duplicate

### Requirement: Normalization of the end-to-end reference
Each comparison of an end-to-end reference SHALL use a normalized form. The
system SHALL remove each whitespace character, each period, and each hyphen,
and SHALL then change the text to upper case. The system SHALL store the
original text, so that each report and each page names what the bank wrote.

#### Scenario: The description wraps inside the reference
- **WHEN** one form holds the reference `30-05-2026 13:49 7180855028127978` and
  the other form holds `30-05-2026 13:49 718085 5028127978`
- **THEN** the system treats the two values as one reference

#### Scenario: The two forms use different separators
- **WHEN** one form holds the reference `8022764496926345` and the other form
  holds `8022.7644 .9692.6345`
- **THEN** the system treats the two values as one reference

#### Scenario: The system stores the reference
- **WHEN** the system stores a transaction whose reference reads
  `8022.7644 .9692.6345`
- **THEN** the stored value keeps each separator, and each comparison uses the
  normalized form

### Requirement: References that the duplicate check ignores
The duplicate check SHALL ignore an end-to-end reference that identifies no
single payment. It SHALL ignore an empty value, the value `NONREF`, and the
value `NOTPROVIDED`. The comparison SHALL use the normalized form, because an
MT940 description wraps at a fixed width and splits the value. For such a
transaction the check SHALL use the transaction id only.

#### Scenario: The statement holds the value NOTPROVIDED
- **WHEN** a statement holds many transactions with the reference `NOTPROVIDED`
- **THEN** the system counts none of them as a duplicate of another one

#### Scenario: The statement holds the value NONREF
- **WHEN** a statement holds many transactions with the reference `NONREF`
- **THEN** the system counts none of them as a duplicate of another one

#### Scenario: The description splits the value
- **WHEN** a description holds the reference `NOTP ROVIDED` or `NOT-PROVIDED`
- **THEN** the system treats it as the value `NOTPROVIDED`, and it joins no
  payment on it

#### Scenario: The transaction holds no reference
- **WHEN** an incoming transaction holds no end-to-end reference
- **THEN** the system compares its transaction id only

### Requirement: The transaction id does not change
The system SHALL NOT derive the transaction id from the end-to-end reference.
The id of each already imported transaction SHALL stay the same after this
change. The manual categorization of each row therefore survives.

#### Scenario: The user imports a known statement again
- **WHEN** the user imports a statement that the system imported before this
  change
- **THEN** the system reports each transaction as a duplicate, and it writes no
  second row

### Requirement: The snapshot import stores the end-to-end reference
The snapshot import SHALL store the end-to-end reference of each row that it
writes. When the snapshot holds no value for that field, the system SHALL derive
the value from the structured description of the row. A snapshot from an app
before this change holds no such field.

#### Scenario: The snapshot holds the field
- **WHEN** a snapshot from the present app holds the end-to-end reference of a
  row
- **THEN** the import writes that value to the row

#### Scenario: The snapshot holds no field
- **WHEN** a snapshot from an app before this change holds a SEPA row with the
  end-to-end reference in its structured description
- **THEN** the import derives the value, and the row holds it

#### Scenario: A later import sees the snapshot row
- **WHEN** the user imports a statement that reports a payment that a snapshot
  already supplied
- **THEN** the duplicate check matches the reference of the snapshot row, and it
  writes no second row

### Requirement: The snapshot import does not use the reference check
The snapshot import SHALL NOT use the duplicate check. It stays the only path
that may replace a stored row. It writes each row by its id, with a report.

#### Scenario: A snapshot holds a transaction with a known reference
- **WHEN** a snapshot holds a transaction whose end-to-end reference matches a
  stored row with another id
- **THEN** the snapshot import writes the snapshot row, and the reference check
  blocks nothing
