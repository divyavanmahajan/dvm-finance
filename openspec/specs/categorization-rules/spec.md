# Categorization Rules Specification

## Purpose

This capability lets the user define, inspect, and maintain the rules that
assign a category and tags to a transaction. The user can also create a rule
directly from a transaction that needs one.

## Requirements

### Requirement: Rule definition
A rule SHALL hold a priority, a match pattern, and a match value. It SHALL also
hold an optional field target, an optional category, optional tags, an active
flag, a tag-only flag, and optional notes. It SHALL also hold optional context
filters for the account, the currency, and a date range. Each rule SHALL hold a
stable UUID from its creation, so that the rules merge across machines without a
heuristic.

#### Scenario: The user opens the new-rule form
- **WHEN** the user opens the new-rule form
- **THEN** the form offers the priority 100, the `contains` pattern, the
  `description` field target, and an active rule that is not tag-only

#### Scenario: The system creates a rule
- **WHEN** the system creates a rule
- **THEN** the rule receives a UUID that never changes across its life

### Requirement: Rule validation
The system SHALL reject a rule whose match pattern is not `contains`, `exact`,
`starts_with`, `ends_with`, or `regex`. It SHALL reject an empty match value and
a regular expression that does not compile. It SHALL reject an extra condition
without a field or a value, with an invalid pattern, or with an operator other
than `AND` or `OR`. The system SHALL render the editor again with each error,
respond with status 400, and write nothing.

#### Scenario: The regular expression does not compile
- **WHEN** the user saves a `regex` rule whose pattern does not compile
- **THEN** the editor shows an error that names the invalid regular expression,
  and the system stores no rule

#### Scenario: The rule holds no category
- **WHEN** the user saves a rule that is not tag-only with no category
- **THEN** the editor shows the error "category is required"

#### Scenario: The tag-only rule holds no tag
- **WHEN** the user saves a tag-only rule with no tag
- **THEN** the editor shows the error "tags is required"

### Requirement: Extra conditions
A rule SHALL support any count of extra conditions. Each condition SHALL hold a
field target, a match pattern, a match value, an `AND` or `OR` operator, and a
sort order. The system SHALL discard a blank condition row. The system SHALL
store the conditions in their sort order. A save SHALL replace each condition of
the rule.

#### Scenario: One row is blank
- **WHEN** the editor submits three condition rows, and one row holds neither a
  field nor a value
- **THEN** the system stores two conditions

#### Scenario: The user saves fewer conditions
- **WHEN** the user saves a rule that held two conditions with one condition
- **THEN** the rule holds exactly that one condition afterwards

### Requirement: Rule list
The system SHALL list the rules in a category-rule tab and a tag-only tab. Each
row SHALL show the definition of the rule, its active state, and the count of
the transactions that the rule currently holds. The count of each tab SHALL stay
visible.

#### Scenario: The user opens the page with no sort
- **WHEN** the user opens the rules page with no sort
- **THEN** the system orders the rules by ascending priority and breaks a tie on
  the id

#### Scenario: The user clicks a column header
- **WHEN** the user clicks the Priority, the Category, or the Match value header
- **THEN** the list sorts on that column, and a second click reverses the order

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

### Requirement: Activation and deactivation of a rule
The system SHALL let the user toggle the active state of a rule without an edit.
Only an active rule SHALL take part in the categorization.

#### Scenario: The user deactivates a rule
- **WHEN** the user toggles an active rule off
- **THEN** the rule stops matching
- **AND** the system recategorizes the transactions that the rule held with the
  remaining rules

### Requirement: Deletion of a rule
The system SHALL let the user delete a rule. The system SHALL then recategorize
the transactions that the rule held with the remaining rules.

#### Scenario: The deleted rule was the only match
- **WHEN** the user deletes the only rule that matched a transaction
- **THEN** that transaction becomes uncategorized, unless another rule matches it

### Requirement: Feedback after a save
After a create or an update, the system SHALL return the user to the rule list.
The page SHALL show a confirmation that names the saved rule, the count of the
changed transactions, and a link to the stored change report.

#### Scenario: A create changes twelve transactions
- **WHEN** the system creates a rule, and 12 transactions change
- **THEN** the rules page shows a confirmation with 12 changed transactions and
  a link to the report

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
