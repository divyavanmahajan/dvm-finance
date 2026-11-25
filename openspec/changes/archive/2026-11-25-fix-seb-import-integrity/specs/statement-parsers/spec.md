## MODIFIED Requirements

### Requirement: Provider identifiers
The PayPal, Wise, SEB, and First Tech parsers SHALL each carry the transaction
identifier of their format. The system derives the transaction identity from
that value. The First Tech parser SHALL remove the commas from the FITID and
SHALL join its parts with `-`, because the identity goes into URL paths. The
SEB parser SHALL carry the voucher number, the krona amount, and the krona
balance, because SEB gives one voucher number to many transactions.

#### Scenario: The system parses an SEB export
- **WHEN** the system parses an SEB export
- **THEN** each transaction carries its voucher number, its krona amount, and
  its krona balance

#### Scenario: The FITID holds spaces and commas
- **WHEN** a First Tech FITID reads `20261113 100002 1,049 7,693`
- **THEN** the identifier is `20261113-100002-1049-7693`
- **AND** the structured description keeps `20261113 100002 1,049 7,693`

### Requirement: Conversion of an SEB amount to the euro
The SEB parser SHALL convert each amount to the euro with the published euro
reference rates. It SHALL prefer the exact date of the transaction, and
otherwise the most recent earlier published day. The structured description
SHALL keep the native amount. If the parser cannot get a rate for each
transaction, it SHALL refuse the file, and the import SHALL write no row.

#### Scenario: The date has no published rate
- **WHEN** a transaction falls on a day with no published rate
- **THEN** the parser uses the most recent earlier published rate

#### Scenario: The rates are not available
- **WHEN** the parser cannot fetch the reference rates
- **THEN** the import refuses the file, writes no row, and tells the user that
  the ECB rates are not available and to try again later

### Requirement: Conversion of a First Tech amount to the euro
The First Tech parser SHALL read each amount as an exact decimal. It SHALL
convert each amount to the euro with the ECB reference rate of the transaction
date, or of the most recent earlier published day. It SHALL round the euro
amount one time, to 2 places, half up. The structured description SHALL keep
the native amount, the native currency, and the rate. If the parser cannot get
a rate for each transaction, it SHALL refuse the file, and the import SHALL
write no row.

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
- **THEN** the import refuses the file, writes no row, and tells the user that
  the ECB rates are not available and to try again later
