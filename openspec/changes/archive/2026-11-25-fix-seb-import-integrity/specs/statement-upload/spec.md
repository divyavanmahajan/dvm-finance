## MODIFIED Requirements

### Requirement: Correction of a stored amount
When an incoming transaction has the id of a stored transaction, the same
currency, and a different amount, the import SHALL replace the stored amount
with the incoming amount. The import SHALL keep each other field of the stored
transaction. The import SHALL count the transaction as corrected, and not as a
duplicate. The import SHALL NOT change a flagged transaction. The import SHALL
NOT change the amount when the currencies are different.

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

#### Scenario: The currencies are different
- **WHEN** the database holds a transaction of -36.52 EUR, and the import gives
  the same id the amount -412.30 SEK
- **THEN** the import counts it as a duplicate, and the stored amount stays
  -36.52 EUR
