# Transfer Exclusion Specification

## Purpose

This capability keeps the movements between the accounts of the user out of the
financial reports. The totals, the trends, and the budgets then describe the
real spending. This specification is the only normative home for the behavior.
Other capabilities inherit it, and they do not repeat it.

## Requirements

### Requirement: Default exclusion of the transfers
Each transaction list and each aggregation SHALL exclude the transfer
transactions, unless the request includes them. This rule binds seven surfaces.
They are the transactions list, the category trends, the cash flow, and the
budget actuals. They are also the tag usage counts, the match count of each
rule, and the rule preview.

#### Scenario: The user opens the default list
- **WHEN** the user opens the transactions list with no transfer parameter
- **THEN** the rows and the summary totals hold no transaction whose effective
  category marks it as a transfer

#### Scenario: The system computes a default aggregation
- **WHEN** the system computes the trends, the cash flow, or the budget actuals
  with no transfer parameter
- **THEN** a transfer transaction contributes nothing to a cell or a total

### Requirement: Inclusion of the transfers on request
The system SHALL include the transfers when the request sets
`include_transfers` to `1`, `true`, or `True`. Any other value or an absent
parameter means exclusion. The URL SHALL hold the choice. The choice is
therefore per request and shareable, and not a stored setting.

#### Scenario: The request includes the transfers
- **WHEN** the request holds `include_transfers=1`
- **THEN** the transfer transactions appear in the rows and the totals

#### Scenario: The request holds an unknown value
- **WHEN** the request holds `include_transfers=yes`
- **THEN** the system excludes the transfers

#### Scenario: The user follows a link without the parameter
- **WHEN** the user includes the transfers and then follows a link without the
  parameter
- **THEN** the system excludes the transfers again on the new page

### Requirement: Exclusion by a substring match in the views
The seven surfaces above SHALL treat a transaction as a transfer when its
effective category holds the text `transfer`. The comparison ignores the case.

#### Scenario: The category holds the text in the middle
- **WHEN** the effective category of a transaction is `wise-transfer-fee`
- **THEN** those views exclude the transaction by default

#### Scenario: The transaction has no category
- **WHEN** a transaction has no effective category
- **THEN** no view excludes the transaction as a transfer

### Requirement: Prefix match in the transfer-category helper
The shared transfer-category helper SHALL report a transfer only for a category
that equals `transfer`, equals `transfer-paypal`, or starts with `transfer-`.
The comparison ignores the case. This behavior differs from the substring match
in the views, and the iOS companion mirrors this helper.

#### Scenario: The category starts with the prefix
- **WHEN** the caller asks the helper about `transfer-wise`
- **THEN** the helper reports a transfer

#### Scenario: The category holds the text but not the prefix
- **WHEN** the caller asks the helper about `wise-transfer-fee`
- **THEN** the helper reports no transfer, although the views exclude that same
  category

#### Scenario: The category is absent
- **WHEN** the caller asks the helper about an empty or absent category
- **THEN** the helper reports no transfer

### Requirement: Exclusion of a manual transfer category
The system SHALL evaluate the exclusion on the effective category. A manual
transfer category therefore removes the transaction from the default views.

#### Scenario: The user marks a transaction as a transfer
- **WHEN** the user sets the manual category of a transaction to `transfer`
- **THEN** the transaction disappears from the default views until a request
  includes the transfers
