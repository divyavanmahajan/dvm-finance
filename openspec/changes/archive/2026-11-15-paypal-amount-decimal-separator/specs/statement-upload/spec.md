# Spec Delta

## MODIFIED Requirements

### Requirement: Import summary
The system SHALL report the source file name and the count of the new, the
duplicate, the corrected, the categorized, and the uncategorized transactions.
For each corrected transaction, it SHALL report the id, the old amount, and the
new amount. It SHALL report them as an inline fragment for the web UI, and as
structured data for a direct call.

#### Scenario: The user submits the upload from the page
- **WHEN** the user submits the upload from the page
- **THEN** the system returns a summary fragment with those counts

#### Scenario: A client calls the endpoint directly
- **WHEN** a client calls the endpoint without the partial-request header
- **THEN** the system returns the same counts as structured data

#### Scenario: The import corrects one amount
- **WHEN** an import corrects the amount of one stored transaction
- **THEN** the summary shows one corrected transaction with its id, its old
  amount, and its new amount

## ADDED Requirements

### Requirement: Correction of a stored amount
When an incoming transaction has the id of a stored transaction and a different
amount, the import SHALL replace the stored amount with the incoming amount.
The import SHALL keep each other field of the stored transaction. The import
SHALL count the transaction as corrected, and not as a duplicate. The import
SHALL NOT change a flagged transaction.

#### Scenario: A report is imported again after a parser fix
- **WHEN** the database holds a PayPal transaction with the amount -1234, and
  the user imports a report that gives the same id the amount -12.34
- **THEN** the stored amount becomes -12.34, and the summary counts one
  corrected transaction

#### Scenario: The stored transaction holds a manual category
- **WHEN** the import corrects the amount of a transaction with a manual
  category and manual tags
- **THEN** the manual category and the manual tags stay the same

#### Scenario: The amounts are equal
- **WHEN** the incoming transaction has the id and the amount of a stored
  transaction
- **THEN** the import counts it as a duplicate and writes nothing

#### Scenario: The stored transaction is flagged
- **WHEN** the incoming transaction has the id of a flagged transaction and a
  different amount
- **THEN** the import counts it as a duplicate and does not change the amount

#### Scenario: The duplicate comes from the end-to-end reference
- **WHEN** the import finds a stored transaction through the end-to-end
  reference or the counterparty, and not through the id
- **THEN** the import counts it as a duplicate and does not change the amount
