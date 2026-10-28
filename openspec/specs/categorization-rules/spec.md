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
The system SHALL open the rule editor with values from a selected transaction,
and SHALL run the preview at once. The system SHALL derive the match value from
the structured merchant name, the name, or the counterparty, where one is
present. It SHALL otherwise use the IBAN. It SHALL otherwise use the
description. The account of the transaction SHALL seed the account filter, and
its effective category SHALL seed the category of the rule.

#### Scenario: The transaction holds a merchant name
- **WHEN** the source transaction holds a structured merchant name
- **THEN** the prepared rule matches on that field and that value

#### Scenario: The transaction holds an IBAN
- **WHEN** the source transaction holds no merchant name, name, or counterparty,
  but it does hold an IBAN
- **THEN** the prepared rule matches on the IBAN

#### Scenario: The transaction holds no structured field
- **WHEN** the source transaction holds no usable structured field
- **THEN** the prepared rule matches on the text of the description

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
