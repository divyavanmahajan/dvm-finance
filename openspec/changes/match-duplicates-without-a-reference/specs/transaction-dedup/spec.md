# Spec Delta

## ADDED Requirements

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
