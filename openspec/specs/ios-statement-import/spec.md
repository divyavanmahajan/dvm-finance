# iOS Statement Import Specification

## Purpose

This capability lets the phone read a statement file directly. The user can
capture transactions away from the computer.

## Requirements

### Requirement: Import of a statement file
The app SHALL import a statement file that the user selects through the system
file picker. The app SHALL support MT940 and the CSV family: the bank CSV,
PayPal, Wise, and SEB. The app SHALL NOT support a spreadsheet file.

#### Scenario: The user selects a supported file
- **WHEN** the user selects a supported statement file
- **THEN** the app parses the file and imports it

#### Scenario: The user selects a spreadsheet
- **WHEN** the user selects a spreadsheet statement
- **THEN** the app does not support the file, because spreadsheet parsing is out
  of scope

### Requirement: Format choice for an ambiguous file
If the app cannot determine the format of a selected file, the app SHALL ask the
user for the format. The app SHALL let the user cancel.

#### Scenario: The user selects an ambiguous CSV
- **WHEN** the user selects a CSV that could be one of several provider formats
- **THEN** the app asks the user for the format before it parses the file

### Requirement: Parity of the import pipeline
A file import SHALL parse the file. It SHALL remove the duplicates with the same
deterministic ids as the desktop application. It SHALL insert the new
transactions. It SHALL apply the rules from the last imported snapshot to them.
It SHALL record an import change report.

#### Scenario: The user imports the same file twice
- **WHEN** the user imports a file that the app already imported
- **THEN** the app reports each transaction as a duplicate and inserts nothing
  twice

#### Scenario: The app applies the rules to the new transactions
- **WHEN** the user imports a file, and the rules from a snapshot are present
- **THEN** the app categorizes the new transactions with those rules and records
  the run as an import change report

### Requirement: Parity of the structured description
The app SHALL fill the structured description exactly as the desktop application
does, because an imported rule matches on those fields.

#### Scenario: A structured-field rule runs on the phone
- **WHEN** a rule from a snapshot matches on a structured field
- **THEN** the rule matches the same transactions on the phone as on the desktop
  application

### Requirement: Import summary
After an import, the app SHALL show the count of the imported transactions, the
skipped duplicates, and the categorized transactions.

#### Scenario: An import ends
- **WHEN** an import ends
- **THEN** the app shows those three counts

### Requirement: Browsable audit history
The app SHALL offer read-only history views of its snapshot imports and its
change reports. Each view SHALL show the items of each record.

#### Scenario: The user opens the import history
- **WHEN** the user opens the import history
- **THEN** the app lists the past imports and change reports with their items
