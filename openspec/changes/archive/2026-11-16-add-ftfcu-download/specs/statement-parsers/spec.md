# Spec Delta

## MODIFIED Requirements

### Requirement: Explicit selection of a provider format
The system SHALL parse a PayPal, a Wise, an SEB, or a First Tech export only
when the user selects that format. The PayPal, Wise, and SEB formats share the
extensions `.csv` and `.txt` with other formats. The automatic detection SHALL
NOT select the First Tech parser for a `.ofx` file.

#### Scenario: The user imports a Wise CSV with automatic detection
- **WHEN** the user imports a Wise CSV with automatic detection
- **THEN** the system uses the generic delimited parser, and not the Wise parser

#### Scenario: The user imports a First Tech OFX with automatic detection
- **WHEN** the user imports a First Tech `.ofx` file with automatic detection
- **THEN** the system refuses the file, because the extension is unknown

### Requirement: Provider identifiers
The PayPal, Wise, SEB, and First Tech parsers SHALL each carry the transaction
identifier of their format. The system derives the transaction identity from
that value. The First Tech parser SHALL remove the commas from the FITID and
SHALL join its parts with `-`, because the identity goes into URL paths.

#### Scenario: The system parses an SEB export
- **WHEN** the system parses an SEB export
- **THEN** each transaction carries its voucher number

#### Scenario: The FITID holds spaces and commas
- **WHEN** a First Tech FITID reads `20261113 100002 1,049 7,693`
- **THEN** the identifier is `20261113-100002-1049-7693`
- **AND** the structured description keeps `20261113 100002 1,049 7,693`

## ADDED Requirements

### Requirement: First Tech OFX file
The First Tech parser SHALL read the OFX 1.02 export of First Tech Federal
Credit Union. It SHALL read each account in the file, including a credit line
in the bank message set. The account SHALL be `ftfcu:` and the last 4 digits of
the account number. The parser SHALL NOT store the full account number. The
parser SHALL refuse a QFX file, an OFX file from another institution, and a
file that is not OFX.

#### Scenario: One file holds four accounts
- **WHEN** the file holds two savings accounts, a checking account, and a
  credit line
- **THEN** the parser reads the transactions of each account, and each
  transaction names `ftfcu:` and the last 4 digits of its account

#### Scenario: The account number is a card number
- **WHEN** the account number of the credit line has 16 digits
- **THEN** no stored field holds the 16 digits

#### Scenario: The user imports a QFX file
- **WHEN** the user imports a First Tech `.qfx` file with the First Tech format
- **THEN** the system refuses the file and tells the user to download OFX

#### Scenario: The date has no time
- **WHEN** a posted date reads `20261105` without a time
- **THEN** the transaction date is 2026-11-05

### Requirement: Conversion of a First Tech amount to the euro
The First Tech parser SHALL read each amount as an exact decimal. It SHALL
convert each amount to the euro with the ECB reference rate of the transaction
date, or of the most recent earlier published day. It SHALL round the euro
amount one time, to 2 places, half up. The structured description SHALL keep
the native amount, the native currency, and the rate. Without rates, the parser
SHALL store US dollars.

#### Scenario: The decimal separator is a period
- **WHEN** the amount reads `-10.49`
- **THEN** the native amount is -10.49, and the parser does not read the period
  as a thousands separator

#### Scenario: The amount is larger than one thousand
- **WHEN** the amount reads `1234.56` and the rate is 1.25
- **THEN** the native amount is 1234.56, and the euro amount is 987.65

#### Scenario: The date has no published rate
- **WHEN** a transaction falls on a day with no published rate
- **THEN** the parser uses the most recent earlier published rate

#### Scenario: The rates are not available
- **WHEN** the parser cannot fetch the reference rates
- **THEN** it stores the transactions in US dollars

### Requirement: Conversion of a PayPal amount to the euro
The PayPal parser SHALL convert a payment in another currency to the euro. It
SHALL use the EUR amount of a linked EUR funding row. Without that row, and for
a bank deposit or a withdrawal in another currency, it SHALL use the ECB
reference rate, as the SEB parser does. The structured description SHALL keep
the original amount and currency. Without a rate, the parser SHALL store the
original currency.

#### Scenario: A funding row exists
- **WHEN** a USD payment has a linked bank deposit of 4.62 EUR
- **THEN** the parser stores -4.62 EUR, and it does not fetch a rate

#### Scenario: No funding row exists
- **WHEN** a USD subscription of -6.90 has no funding row, and the most recent
  rate on or before its date is 1.15
- **THEN** the parser stores -6.00 EUR, and the structured description keeps
  -6.90 USD and the rate 1.15

#### Scenario: The bank deposit is in US dollars
- **WHEN** a bank deposit of 6.90 USD funds the subscription, at the rate 1.15
- **THEN** the parser stores +6.00 EUR, and it does not label the dollar amount
  as euro

#### Scenario: The rates are not available
- **WHEN** the parser cannot fetch the reference rates
- **THEN** it stores the subscription in US dollars
