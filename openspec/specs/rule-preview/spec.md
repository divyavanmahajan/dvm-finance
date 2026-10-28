# Rule Preview Specification

## Purpose

A preview shows the user what a draft rule does, before the system saves it. No
rule change is therefore a surprise.

## Requirements

### Requirement: Preview of a draft without a save
The system SHALL evaluate a draft rule from the editor and report its effect.
The system SHALL write nothing to the database. A preview SHALL work for a rule
that does not exist yet, and for an edit to an existing rule.

#### Scenario: The user previews a new rule
- **WHEN** the user fills in the new-rule form and asks for a preview
- **THEN** the system reports the effect and creates no rule

#### Scenario: The user previews an edit
- **WHEN** the preview request names the rule under edit
- **THEN** the system simulates the draft in place of the current definition of
  that rule

### Requirement: Reported effect
A preview SHALL report four sets with a count for each one. The first set holds
the transactions that the draft matches. The second set holds the transactions
that the draft claims for the first time. The third set holds the transactions
that the edited rule held and the draft no longer matches. The fourth set holds
the change to the category and the tags of each affected transaction.

#### Scenario: The user narrows an existing rule
- **WHEN** the user narrows an existing rule, and it no longer matches some
  transactions that it categorized
- **THEN** the preview reports those transactions as losses

#### Scenario: A new draft claims unclaimed transactions
- **WHEN** a new draft rule claims transactions that no rule claimed before
- **THEN** the preview reports those transactions as gains

### Requirement: Simulation against the complete rule set
The system SHALL compute the change list with the draft in place inside the
complete set of active rules. It SHALL sort the set by the priority and then the
id, and resolve each transaction to the first match. A draft that loses to a
rule of a higher priority therefore reports no change.

#### Scenario: A rule of a higher priority wins
- **WHEN** the draft matches a transaction that an active rule of a higher
  priority also matches
- **THEN** the preview reports the transaction as matched, but not as a change

### Requirement: Scope of a preview
A preview SHALL skip each transaction whose categorization source is manual. It
SHALL exclude the transfer transactions, unless the request includes them.

#### Scenario: The request includes the transfers
- **WHEN** the preview request includes the transfers
- **THEN** the transfer transactions appear in the reported sets

### Requirement: Validation feedback from a preview
For an empty match value, the preview SHALL ask the user for one. For a regular
expression that does not compile, the preview SHALL report that error. In both
cases the system SHALL return no result, and the request SHALL NOT fail.

#### Scenario: The match value is empty
- **WHEN** the user asks for a preview with no match value
- **THEN** the response asks the user for a match value

#### Scenario: The regular expression does not compile
- **WHEN** the user asks for a preview with a regular expression that does not
  compile
- **THEN** the response reports the error in the regular expression

### Requirement: Display cap for a preview
The preview SHALL show at most 100 transactions for each reported set. The
preview SHALL still report the complete count.

#### Scenario: The draft matches many transactions
- **WHEN** a draft matches 5,000 transactions
- **THEN** the count reports 5,000, and the page lists at most 100 rows

### Requirement: Automatic preview for a rule from a transaction
When the system opens the editor with values from a transaction, the preview
SHALL run at once. The user therefore sees the reach of the rule before any
edit.

#### Scenario: The user starts a rule from a transaction
- **WHEN** the user selects "create rule from this transaction"
- **THEN** the editor opens, and it already holds the preview
