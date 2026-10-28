# Statement Parsers Specification

## Purpose

The parsers turn each statement format of the banks and the payment providers
into transactions. They also fill the structured description fields that the
rules match on.

## Requirements

### Requirement: Format detection by the file extension
With no explicit format, the system SHALL select the parser by the file
extension. It SHALL use the MT940 parser for `.mt940`, `.mta`, `.sta`, and
`.txt`. It SHALL use the spreadsheet parser for `.xls` and `.xlsx`. It SHALL use
the generic delimited parser for `.csv`. It SHALL refuse each other extension.

#### Scenario: The file has an MT940 extension
- **WHEN** the user imports a `.sta` file with automatic detection
- **THEN** the system uses the MT940 parser

#### Scenario: The extension is unknown
- **WHEN** the user imports a file with an unknown extension and automatic
  detection
- **THEN** the system refuses the file with a message that names the format

### Requirement: Explicit selection of a provider format
The system SHALL parse a PayPal, a Wise, or an SEB export only when the user
selects that format. These formats share the extensions `.csv` and `.txt` with
other formats.

#### Scenario: The user imports a Wise CSV with automatic detection
- **WHEN** the user imports a Wise CSV with automatic detection
- **THEN** the system uses the generic delimited parser, and not the Wise parser

### Requirement: Transaction fields from a parser
Each parser SHALL produce the fields that its format holds. They are the account
number, the transaction date, the value date, the amount, the currency, and the
raw description. They are also the start balance, the end balance, the source
file, and the source line.

#### Scenario: The system parses a statement
- **WHEN** the system parses a statement
- **THEN** each transaction records the file that it came from and its line in
  that file

### Requirement: Structured description from a parser
Each parser SHALL store the fields of its own format as a structured
description, beside the raw text. The rules match on those fields.

#### Scenario: The MT940 description holds tagged fields
- **WHEN** an MT940 description holds tagged fields such as the IBAN, the name,
  and the remittance information of the counterparty
- **THEN** the system makes those fields available as structured values for the
  rules

#### Scenario: A provider export holds columns
- **WHEN** the system parses a PayPal, a Wise, or an SEB export
- **THEN** the structured description keeps the original columns

### Requirement: Tolerance for the column names
The spreadsheet parser and the generic delimited parser SHALL accept the common
spellings of each standard column name. The comparison ignores the case.

#### Scenario: The CSV uses alternate spellings
- **WHEN** a CSV names its columns `account_number`, `transaction_date`, and
  `date`
- **THEN** the system maps them to the account field and the transaction-date
  field

### Requirement: Provider identifiers
The PayPal parser, the Wise parser, and the SEB parser SHALL each carry the
transaction identifier of their format. They are the PayPal transaction id, the
Wise transaction id, and the SEB voucher number. The system derives the
transaction identity from that value.

#### Scenario: The system parses an SEB export
- **WHEN** the system parses an SEB export
- **THEN** each transaction carries its voucher number

### Requirement: European amount format
The PayPal parser SHALL read the European number format. A comma is the decimal
separator, and a period is the thousands separator.

#### Scenario: The amount uses the European format
- **WHEN** a PayPal amount reads `1.458,32`
- **THEN** the system parses the value 1458.32

### Requirement: Conversion of a Wise amount to the euro
The Wise parser SHALL convert an outgoing transaction to the euro. It SHALL use
the euro rate of the most recent earlier top-up that loaded that currency from
the euro. It SHALL look in the file under the parse first, and then among the
transactions from an earlier import. The conversion SHALL use only the source
currency. Without a rate, the parser SHALL store the native currency.

#### Scenario: An earlier top-up gives the rate
- **WHEN** an outgoing payment in Swedish krona follows a top-up from the euro
  into krona
- **THEN** the parser converts the payment at the rate of that top-up

#### Scenario: The source and the target are both not the euro
- **WHEN** a krona wallet pays a merchant in Norwegian krone
- **THEN** the parser converts only the krona source amount, because Wise
  already made the internal conversion

#### Scenario: No rate exists
- **WHEN** no top-up from the euro comes before the transaction in the file or
  the database
- **THEN** the parser stores the native currency

### Requirement: Conversion of an SEB amount to the euro
The SEB parser SHALL convert each amount to the euro with the published euro
reference rates. It SHALL prefer the exact date of the transaction, and
otherwise the most recent earlier published day. The structured description
SHALL keep the native amount. If the parser cannot fetch the rates, it SHALL
store the amounts in krona.

#### Scenario: The date has no published rate
- **WHEN** a transaction falls on a day with no published rate
- **THEN** the parser uses the most recent earlier published rate

#### Scenario: The rates are not available
- **WHEN** the parser cannot fetch the reference rates
- **THEN** it stores the transactions in krona
