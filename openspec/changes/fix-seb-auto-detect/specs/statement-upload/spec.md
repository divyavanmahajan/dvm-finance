## MODIFIED Requirements

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
