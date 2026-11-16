# Spec Delta

## MODIFIED Requirements

### Requirement: Detail view for a row
The system SHALL provide a detail view for each transaction. The view SHALL show
each stored field, the key and value pairs of the parsed structured description,
and the rule that assigned the current category. For a converted transaction,
the view SHALL also show the original amount, the original currency, and the
rate when the parser recorded one.

#### Scenario: The user opens the detail of a rule-categorized transaction
- **WHEN** the user opens the detail view of a transaction whose categorization
  source is a rule
- **THEN** the view shows the structured description fields and names that rule

#### Scenario: The request names an unknown transaction
- **WHEN** a detail request names a transaction id that does not exist
- **THEN** the system responds with status 404

#### Scenario: The user opens the detail of a converted transaction
- **WHEN** the user opens the detail view of a transaction that the parser
  converted from 10.49 US dollars at the rate 1.25
- **THEN** the view shows `-10.49 USD` and `rate 1.25 USD for 1 EUR`

## ADDED Requirements

### Requirement: Original amount beside the euro amount
The transactions table SHALL show the original amount and the original currency
of each converted transaction, before the stored amount. A transaction is
converted when its structured description holds an original currency that
differs from the stored currency. The original amount SHALL have the sign of the
stored amount.

#### Scenario: A First Tech payment in dollars
- **WHEN** a transaction holds -8.39 EUR and the native amount -10.49 USD
- **THEN** the amount cell shows `-10.49 USD` and then `-8.39 EUR`

#### Scenario: Wise keeps the amount without a sign
- **WHEN** a Wise payment holds -9.13 EUR and the native amount `100.00` SEK
- **THEN** the amount cell shows `-100.00 SEK` before the euro amount

#### Scenario: A PayPal payment in dollars
- **WHEN** a PayPal transaction holds `original_amount` -5.00 and
  `original_currency` USD, and the stored currency is EUR
- **THEN** the amount cell shows `-5.00 USD` before the euro amount

#### Scenario: The original amount is not a valid decimal
- **WHEN** the native amount reads `1,00`
- **THEN** the amount cell shows only the stored amount

#### Scenario: The rates were not available
- **WHEN** a First Tech transaction is stored in US dollars
- **THEN** the amount cell shows only the dollar amount
