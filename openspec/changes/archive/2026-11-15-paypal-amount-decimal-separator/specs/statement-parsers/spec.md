# Spec Delta

## MODIFIED Requirements

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
