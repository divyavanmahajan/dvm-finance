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
description, beside the raw text. The rules match on those fields. Two
description forms of one payment type SHALL use the same key for the same
meaning.

#### Scenario: The MT940 description holds tagged fields
- **WHEN** an MT940 description holds tagged fields such as the IBAN, the name,
  and the remittance information of the counterparty
- **THEN** the system makes those fields available as structured values for the
  rules

#### Scenario: A provider export holds columns
- **WHEN** the system parses a PayPal, a Wise, or an SEB export
- **THEN** the structured description keeps the original columns

#### Scenario: The two SEPA forms describe one payment
- **WHEN** the system parses the tagged form and the labelled form of one SEPA
  direct debit
- **THEN** the two structured descriptions hold the same key and the same value
  for the creditor identifier, the mandate reference, the IBAN, the name, the
  remittance information, and the end-to-end reference

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
The PayPal parser SHALL find the decimal separator from each amount. When the
last period or comma of the amount has one or two digits after it, that
character SHALL be the decimal separator. Each other period or comma SHALL be a
thousands separator. An amount with no such character SHALL be a whole number.
The iOS parser SHALL give the same value for each amount.

#### Scenario: The amount uses the European format
- **WHEN** a PayPal amount reads `1.458,32`
- **THEN** the system parses the value 1458.32

#### Scenario: The amount uses a comma as the decimal separator
- **WHEN** a PayPal amount reads `-12,34`
- **THEN** the system parses the value -12.34

#### Scenario: The amount uses a period as the decimal separator
- **WHEN** a PayPal amount reads `-12.34`
- **THEN** the system parses the value -12.34

#### Scenario: The amount uses a period as the decimal separator and a thousands separator
- **WHEN** a PayPal amount reads `1,458.32`
- **THEN** the system parses the value 1458.32

#### Scenario: The amount has a thousands separator and no decimals
- **WHEN** a PayPal amount reads `1.458`
- **THEN** the system parses the value 1458

#### Scenario: The amount has one decimal
- **WHEN** a PayPal amount reads `1,5`
- **THEN** the system parses the value 1.5

#### Scenario: The amount is not a number
- **WHEN** a PayPal amount reads `abc`
- **THEN** the parser returns no amount for that field

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

### Requirement: Canonical keys of a SEPA description
The system SHALL use one set of keys for a SEPA payment. They are
`creditor_identifier`, `mandate_reference`, `remittance_info`,
`end_to_end_reference`, `iban`, `bic`, and `name`. The tagged form and the
labelled form SHALL both use these keys.

#### Scenario: The tagged form holds the creditor identifier
- **WHEN** a description holds `/CSID/VP20XNL847867841319`
- **THEN** the structured description holds `creditor_identifier` with the value
  `VP20XNL847867841319`, and it holds no `CSID` entry

#### Scenario: The tagged form holds the mandate reference
- **WHEN** a description holds `/MARF/B0OXIVC5T2O3ZJ58`
- **THEN** the structured description holds `mandate_reference` with the value
  `B0OXIVC5T2O3ZJ58`

#### Scenario: The labelled form holds the remittance information
- **WHEN** a description holds `OMSCHRIJVING: LEBARA NL-03944254 3-277`
- **THEN** the structured description holds `remittance_info`, and it holds no
  `description` entry

#### Scenario: The labelled form holds the reference
- **WHEN** a description holds `KENMERK: KFF5Q4D85TQK39G6`
- **THEN** the structured description holds `end_to_end_reference`, and it holds
  no `reference` entry

### Requirement: Normalized SEPA transaction type
The system SHALL give the same normalized `transaction_type` to the tagged form
and to the labelled form. The system SHALL also report `sepa_type`. For a direct
debit the system SHALL report `direct_debit_type` and `recurring` when the text
names them.

#### Scenario: The tagged form names a recurring direct debit
- **WHEN** a description holds `/TRTP/SEPA INCASSO ALGEMEEN DOORLOPEND`
- **THEN** `transaction_type` is `SEPA Direct Debit`, `sepa_type` is `INCASSO`,
  `direct_debit_type` is `General`, and `recurring` is true

#### Scenario: The tagged form names a transfer
- **WHEN** a description holds `/TRTP/SEPA OVERBOEKING`
- **THEN** `transaction_type` is `SEPA Transfer`, and `sepa_type` is
  `OVERBOEKING`

### Requirement: The format value of a SEPA description
The system SHALL report the format `sepa` for each description that names a SEPA
payment, in the tagged form and in the labelled form. The system SHALL keep the
format `mt940` for a tagged description that names another payment type.

#### Scenario: The tagged form names a SEPA payment
- **WHEN** the `/TRTP/` value starts with `SEPA`
- **THEN** the format is `sepa`

#### Scenario: The tagged form names another type
- **WHEN** the `/TRTP/` value is `IDEAL`
- **THEN** the format stays `mt940`

### Requirement: The Tikkie branch uses the SEPA type
The system SHALL select the Tikkie extraction by `sepa_type`, and not by the
display text of `transaction_type`. The system SHALL extract the same Tikkie
fields from the tagged form as before this change.

#### Scenario: The tagged form holds a Tikkie transfer
- **WHEN** a tagged description holds `/TRTP/SEPA OVERBOEKING` and a remittance
  text that starts with `TIKKIE ID`
- **THEN** the structured description holds `tikkie_id`, `payer_name`, and
  `payer_iban`

### Requirement: The stored structured description uses the canonical keys
The system SHALL rewrite the stored structured description of each SEPA
transaction with the canonical keys, one time. The rules read the stored value,
so a rule on a canonical key SHALL match a row from before this change.

#### Scenario: A stored tagged row holds the old format
- **WHEN** a stored row holds the format `mt940` and a `transaction_type` that
  starts with `SEPA`
- **THEN** the system rewrites its structured description, and the row holds
  `creditor_identifier` and `mandate_reference`

#### Scenario: A stored labelled row holds the old keys
- **WHEN** a stored row holds the format `sepa` with the keys `description` and
  `reference`
- **THEN** the system rewrites its structured description to `remittance_info`
  and `end_to_end_reference`

#### Scenario: A rule matches a row from before the change
- **WHEN** a rule names the field target `end_to_end_reference`, and a row from
  before this change holds that reference
- **THEN** the rule matches that row

#### Scenario: A row holds no SEPA description
- **WHEN** a stored row holds the format `pos`
- **THEN** the system does not change its structured description
