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

### Requirement: A second key for a transaction with no reference
The duplicate check SHALL use a second key for a transaction that holds no
usable end-to-end reference. The key is the account, the transaction date, the
amount, the counterparty IBAN, and the remittance text. A transfer between two
accounts of the user carries no reference, so only this key joins its two
description forms.

#### Scenario: Two forms of a transfer with no reference
- **WHEN** one statement reports a transfer of -1000,00 euro with the tagged
  form, and a second statement reports the same transfer with the labelled form,
  and both hold the reference `NOTPROVIDED`
- **THEN** the system counts the second one as a duplicate

#### Scenario: The transaction holds a usable reference
- **WHEN** a transaction holds a usable end-to-end reference
- **THEN** the system uses the reference key only, and it does not use this key

#### Scenario: The transaction holds no counterparty IBAN
- **WHEN** a transaction holds no usable reference and no counterparty IBAN
- **THEN** the system compares its transaction id only

### Requirement: Normalization of the second key
The system SHALL normalize the counterparty IBAN and the remittance text with
the same rule as the end-to-end reference. The system SHALL remove each
whitespace character, each period, and each hyphen, and SHALL then change the
text to upper case.

#### Scenario: The description wraps inside the remittance text
- **WHEN** one form holds the remittance text `JYNQ VAN LCJFOST` and the other
  form holds `JYNQ VAN LCJFO ST`
- **THEN** the system treats the two values as one remittance text

### Requirement: The remittance text belongs to the second key
The second key SHALL hold the remittance text. Two payments of one day can
share an account, an amount, and a counterparty. Only the remittance text tells
them apart.

#### Scenario: Three payments of one day share the counterparty
- **WHEN** one account holds three payments of -149,00 euro of one day to one
  IBAN, with the remittance texts `1881164974955/PAYPAL`,
  `3404065959685/PAYPAL`, and `7624611028858/PAYPAL`
- **THEN** the system counts none of them as a duplicate of another one

#### Scenario: The remittance text is absent
- **WHEN** a transfer holds no remittance text
- **THEN** the key holds an empty remittance text, and the rule of the
  statement file below protects the group

### Requirement: One row of each statement file
The system SHALL NOT join two rows of one statement file by the second key. The
two description forms of one payment always come from two statement files,
because the bank changed the form between the two downloads. Two rows of one
file are two payments.

#### Scenario: One file reports two equal payments
- **WHEN** one statement file reports two transfers of one day with the same
  amount, the same IBAN, and the same remittance text
- **THEN** the system counts neither one as a duplicate

#### Scenario: Two files report one payment
- **WHEN** two statement files each report one transfer of one day with the same
  amount, the same IBAN, and the same remittance text
- **THEN** the system counts the second one as a duplicate
