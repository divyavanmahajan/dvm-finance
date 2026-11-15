# Spec Delta

## MODIFIED Requirements

### Requirement: Creation of a rule from a transaction
The system SHALL open the rule editor with the selected transaction as the
sample, and SHALL run the preview at once. The editor SHALL select the first
row that holds a value: the merchant name, the name, the counterparty, the
IBAN, or else the description. It SHALL also select the account filter row.
The effective category of the transaction SHALL seed the rule category.

#### Scenario: The transaction holds a merchant name
- **WHEN** the source transaction holds a structured merchant name
- **THEN** the editor selects only the merchant name row and the account
  filter row, and the prepared rule matches on that field and that value

#### Scenario: The transaction holds an IBAN
- **WHEN** the source transaction holds no merchant name, name, or counterparty,
  but it does hold an IBAN
- **THEN** the editor selects the IBAN row, and the prepared rule matches on
  the IBAN

#### Scenario: The transaction holds no structured field
- **WHEN** the source transaction holds no usable structured field
- **THEN** the editor selects the description row, and the prepared rule
  matches on the text of the description

#### Scenario: The request names an unknown transaction
- **WHEN** the request names a transaction id that does not exist
- **THEN** the system responds with status 404

## ADDED Requirements

### Requirement: Field list from a sample transaction
When the editor has a sample transaction, the Match card SHALL show one row for
each field of that transaction. The list SHALL hold the merchant name, the
name, the counterparty, and the IBAN first, in that order. Each other
structured field SHALL follow. The description SHALL be the last row. The list
SHALL omit a structured field that holds no value.

#### Scenario: The sample holds three structured fields
- **WHEN** the sample transaction holds the structured fields `name`, `iban`,
  and `kenmerk` with values
- **THEN** the field list shows the rows `name`, `iban`, `kenmerk`, and
  `description`, in that order

#### Scenario: A structured field is empty
- **WHEN** the sample transaction holds an empty `merchant_code` field
- **THEN** the field list shows no `merchant_code` row

### Requirement: Content of a field row
Each field row SHALL hold a checkbox, the field name, a pattern selector, and a
value. The pattern selector SHALL offer the valid match patterns. The value
SHALL start as the value from the sample transaction, and the user SHALL be
able to edit it. A new row SHALL start with the `contains` pattern.

#### Scenario: The user edits a value
- **WHEN** the user selects the description row and shortens its value to
  `ALBERT HEIJN`
- **THEN** the preview and the save use `ALBERT HEIJN` as the value of that
  row

### Requirement: Rule from the selected field rows
The field of the first selected row SHALL become the field target of the
primary match. The pattern and the value of that row SHALL become the pattern
and the value of the primary match. Each other selected row SHALL become an
`AND` condition. These conditions SHALL come before each advanced condition.
The system SHALL derive the rule type from the field target, as it does for
each other save.

#### Scenario: The user selects two rows
- **WHEN** the user selects the `name` row and the `description` row
- **THEN** the rule matches on `name`, with one `AND` condition on
  `description`

#### Scenario: The user selects only the IBAN row
- **WHEN** the user selects only the `iban` row
- **THEN** the rule matches on the structured `iban` field with no condition

#### Scenario: The user selects no row
- **WHEN** the field list shows, and the user selects no row and asks for a
  preview
- **THEN** the editor asks the user to select at least one field, and the
  system writes nothing

### Requirement: Context filter rows
The Match card SHALL show the account, the currency, the start date, and the
end date as filter rows below the field rows. Each filter row SHALL hold a
checkbox and a value. The rule SHALL use a filter only when the user selects
its row. With a sample transaction, the account and the currency SHALL start
with the values of that transaction. The right column SHALL hold no filter.

#### Scenario: The user clears the account filter
- **WHEN** the user clears the checkbox of the account filter row and saves
- **THEN** the rule holds no account filter

#### Scenario: The user selects the currency filter
- **WHEN** the sample transaction is in `EUR`, and the user selects the
  currency filter row
- **THEN** the rule holds the currency filter `EUR`

### Requirement: Advanced conditions
The editor SHALL keep the manual condition builder below the field list, with
the name "Advanced conditions". The user SHALL be able to add, remove, and
reorder these conditions, and set `AND` or `OR` on each. The editor SHALL show
the builder also when there is no sample transaction.

#### Scenario: The user adds an OR condition
- **WHEN** the user selects the `name` row and adds an advanced `OR` condition
  on `description`
- **THEN** the rule holds the `name` match, then the `OR` condition

### Requirement: Editor without a sample transaction
When the editor has no sample transaction, the Match card SHALL show the field,
pattern, type, and value inputs of the primary match. It SHALL also show the
advanced conditions and the filter rows. "Edit rule" and a blank new rule SHALL
open in this state.

#### Scenario: The user opens a saved rule
- **WHEN** the user opens "Edit rule" for a saved rule
- **THEN** the editor shows the saved primary match, the saved conditions, and
  the saved filters, and it shows no field list

### Requirement: Sample transaction for a draft
When the user selects "Use as sample" on a preview row, the editor SHALL show
the field list of that transaction. The editor SHALL keep the current draft.
The primary match and the leading `AND` conditions of the draft SHALL become
selected rows with their own pattern and value.

#### Scenario: The sample holds the field of the rule
- **WHEN** the rule matches `name` with `exact` and the value `ACME BV`, and the
  user selects a sample whose `name` is `ACME B.V.`
- **THEN** the `name` row is selected with `exact` and `ACME BV`

#### Scenario: The sample does not hold a field of the rule
- **WHEN** the rule holds an `AND` condition on `kenmerk`, and the sample holds
  no `kenmerk` field
- **THEN** the field list shows a selected `kenmerk` row with the value from the
  rule

#### Scenario: The rule holds an OR condition
- **WHEN** the rule holds the conditions `AND name`, then `OR description`, and
  the user selects a sample
- **THEN** the `name` condition becomes a selected row, and the `OR` condition
  stays in the advanced conditions

#### Scenario: The user changed the category before the sample loads
- **WHEN** the user changes the category and then selects a sample
- **THEN** the editor keeps the changed category

#### Scenario: Two conditions use the same field
- **WHEN** the rule holds two leading `AND` conditions on `description`
- **THEN** the first condition becomes the `description` row, and the second
  condition stays in the advanced conditions
