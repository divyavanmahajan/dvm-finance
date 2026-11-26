# Statement Upload Specification

## Purpose

This capability lets the user send a statement file to the application by hand.
The system imports the file, removes the duplicates, categorizes the new
transactions, and reports what it did.

## Requirements

### Requirement: Upload page and endpoint
The system SHALL offer an Import page at `/import`. The Import page SHALL hold
the download sources first and the upload form after them. The system SHALL
also offer an endpoint that accepts one statement file and an optional format
selection.

#### Scenario: The user opens the upload page
- **WHEN** the user opens the Import page
- **THEN** the page shows a file field and the available format choices

#### Scenario: The user uploads a file from the Import page
- **WHEN** the user submits a statement file from the Import page
- **THEN** the Import page shows the import summary, and the user stays on the
  Import page

### Requirement: Format selection
The system SHALL accept the formats `auto`, `paypal`, `wise`, `seb`, and `csv`.
The default is `auto`, and it selects the parser from the file extension. For a
`.csv` file with the SEB header row, `auto` SHALL select the SEB parser. The
system SHALL reject any other value with status 422.

#### Scenario: The user selects an explicit format
- **WHEN** the user uploads a PayPal activity report with the `paypal` format
- **THEN** the system uses the PayPal parser, whatever the file extension is

#### Scenario: The user uploads an SEB file with the format auto
- **WHEN** the user uploads a `.csv` file with the header row
  `Booking date;Value date;Voucher number;Text;Amount;Balance` and the format
  `auto`
- **THEN** the system uses the SEB parser and stores the SEB transactions

#### Scenario: The user submits an unknown format
- **WHEN** the user submits an unknown format value
- **THEN** the system responds with status 422 and imports nothing

### Requirement: Import pipeline
For an accepted upload, the system SHALL store the file under the statements
folder of the data directory with a unique name. The system SHALL then parse the
file and remove the transactions that the database already holds. It SHALL
insert the remainder. It SHALL apply the active rules to the new transactions.

#### Scenario: The file holds known and unknown transactions
- **WHEN** the user uploads a statement with 40 transactions, and the database
  already holds 10 of them
- **THEN** the system inserts 30 transactions, applies the rules to them, and
  keeps the stored file

#### Scenario: The system stores the file under a generated name
- **WHEN** the system stores a file under a generated unique name
- **THEN** each transaction records the original file name as its source file

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

### Requirement: Rejected uploads
The system SHALL reject an upload that is empty, unparseable, or without a
transaction. It SHALL respond with status 422 and an explanation. It SHALL
import nothing.

#### Scenario: The file is empty
- **WHEN** the user uploads a file of zero bytes
- **THEN** the system responds with status 422 and reports the empty file

#### Scenario: The system cannot parse the file
- **WHEN** the system cannot parse the file
- **THEN** the system responds with status 422, names the file, and suggests an
  explicit format

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
