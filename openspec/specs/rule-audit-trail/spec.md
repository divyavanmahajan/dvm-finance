# Rule Audit Trail Specification

## Purpose

This capability makes each recategorization traceable. Each rule mutation stores
a report of the rule before and after the change, and of each transaction that
moved. No recategorization is silent.

## Requirements

### Requirement: A change report for each rule mutation
A create, an update, a delete, or a toggle of a rule SHALL apply the active
rules again. It SHALL also store a change report. The report SHALL hold the
action, and the id and the UUID of the rule. It SHALL hold the state of the rule
before and after the change. It SHALL hold the count of the changed
transactions. The system SHALL NOT commit a rule mutation without its report.

#### Scenario: The user creates a rule
- **WHEN** the user creates a rule
- **THEN** the system stores a report with the action `create`, no before state,
  and the snapshot of the new rule as the after state

#### Scenario: The user deletes a rule
- **WHEN** the user deletes a rule
- **THEN** the system stores a report with the action `delete`, the snapshot of
  the deleted rule as the before state, and no after state
- **AND** the report keeps the id and the UUID of the rule

#### Scenario: The user toggles a rule
- **WHEN** the user flips the active flag of a rule
- **THEN** the system stores a report with the action `toggle` that holds the
  flag change and the resultant recategorizations

### Requirement: Change items for each transaction
A report SHALL hold one item for each transaction that it changed. Each item
SHALL hold the transaction id, the old and the new category, and the old and the
new tags.

#### Scenario: An update changes eight transactions
- **WHEN** a rule update recategorizes 8 transactions
- **THEN** the summary of the report counts 8, and the system stores 8 items

#### Scenario: A mutation changes no transaction
- **WHEN** the user saves a rule that changes no transaction
- **THEN** the system stores a report with a count of zero and no item

### Requirement: Rule snapshots
A rule snapshot SHALL hold the identity, the priority, the type, the pattern,
and the field target of the rule. It SHALL also hold the match value, the
category, and the tags. It SHALL also hold the active flag, the tag-only flag,
the notes, the context filters, and the ordered conditions. A report is
therefore self-describing after the rule itself is gone.

#### Scenario: The user reads the report of a deleted rule
- **WHEN** the user reads the report of a deleted rule
- **THEN** the report still holds the complete definition of the rule, together
  with its conditions

### Requirement: Reapplication of each rule on demand
The system SHALL offer a recategorize-all action. The action SHALL apply each
active rule to each non-manual transaction. It SHALL store a report with the
action `recategorize`.

#### Scenario: The user triggers recategorize-all
- **WHEN** the user triggers recategorize-all
- **THEN** the system applies the rules again, stores a `recategorize` report,
  and refreshes the match counts in the rule list

### Requirement: History views
The system SHALL show a chronological history of each change report, with the
newest first. The system SHALL also show a history for one rule. A per-rule
history SHALL hold each report that matches the rule id or the rule UUID. The
history of a rule therefore survives a delete and a later import.

#### Scenario: The user opens the history of a deleted rule
- **WHEN** the user opens the history of a deleted rule
- **THEN** the page still lists the reports of that rule

#### Scenario: The user expands a report
- **WHEN** the user expands a report
- **THEN** the report shows the difference between the before and the after
  snapshot for each field
- **AND** it shows each changed transaction with a link to that transaction

### Requirement: Audit of a rename that touches a rule
A tag rename or a category rename that modifies a rule SHALL store a change
report with the action `update` for each affected rule. The report SHALL hold
the before and the after snapshot and the rename that caused the change. Such a
rename SHALL NOT apply the rules again.

#### Scenario: A rename touches two rules
- **WHEN** a tag rename changes the tags of two rules
- **THEN** the system stores two `update` reports, and no recategorization runs

### Requirement: Audit of a snapshot import in the same trail
A snapshot import SHALL store a change report with the action `import`. The
report SHALL hold the change to the effective category and the effective tags of
each transaction. An import therefore appears in the same history as a rule
mutation.

#### Scenario: An import overwrites three categories
- **WHEN** a snapshot import overwrites the category of 3 transactions
- **THEN** the history lists an `import` report with those 3 items
