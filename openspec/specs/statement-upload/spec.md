# Statement Upload Specification

## Purpose

This capability lets the user send a statement file to the application by hand.
The system imports the file, removes the duplicates, categorizes the new
transactions, and reports what it did.

## Requirements

### Requirement: Upload page and endpoint
The system SHALL offer an upload page. The system SHALL also offer an endpoint
that accepts one statement file and an optional format selection.

#### Scenario: The user opens the upload page
- **WHEN** the user opens the upload page
- **THEN** the page shows a file field and the available format choices

### Requirement: Format selection
The system SHALL accept the formats `auto`, `paypal`, `wise`, `seb`, and `csv`.
The default is `auto`, and it selects the parser from the file extension. The
system SHALL reject any other value with status 422.

#### Scenario: The user selects an explicit format
- **WHEN** the user uploads a PayPal activity report with the `paypal` format
- **THEN** the system uses the PayPal parser, whatever the file extension is

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
duplicate, the categorized, and the uncategorized transactions. It SHALL report
them as an inline fragment for the web UI, and as structured data for a direct
call.

#### Scenario: The user submits the upload from the page
- **WHEN** the user submits the upload from the page
- **THEN** the system returns a summary fragment with those counts

#### Scenario: A client calls the endpoint directly
- **WHEN** a client calls the endpoint without the partial-request header
- **THEN** the system returns the same counts as structured data

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
