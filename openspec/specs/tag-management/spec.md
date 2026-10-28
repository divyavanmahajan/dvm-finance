# Tag Management Specification

## Purpose

The tags page shows which tags are in use and how much money each tag covers.
The user can also rename a tag or remove it across the complete dataset.

## Requirements

### Requirement: Tag usage list
The system SHALL list each tag in use with the count of the transactions that
hold it, and with its total credit and debit amount. The order is the descending
count, and then the alphabet. The system SHALL count a tag once for each
transaction, even when the transaction holds it in both tag columns.

#### Scenario: A transaction holds the tag in both columns
- **WHEN** a transaction holds `travel` in both the rule-assigned and the manual
  tags
- **THEN** the count of the tag increases by one for that transaction

#### Scenario: A tag covers a credit and a debit
- **WHEN** a tag covers a transaction of +100 and a transaction of -250
- **THEN** its credit total is 100, and its debit total is 250

### Requirement: Link from a tag into the transactions view
Each listed tag SHALL link to the transactions view with a filter for that tag.

#### Scenario: The user clicks a tag
- **WHEN** the user clicks a tag
- **THEN** the transactions view opens with a filter for that tag

### Requirement: Rename of a tag
A rename SHALL replace the tag in the rule-assigned tags and the manual tags of
each transaction, and in the tags of each rule. The match is a complete
comma-separated entry, and it ignores the case. The system SHALL reject a rename
to an empty value with an error, and it SHALL change nothing.

#### Scenario: The user renames a tag
- **WHEN** the user renames `holiday` to `vacation`
- **THEN** each transaction that holds it in either tag column now holds
  `vacation`
- **AND** each rule that assigns it now assigns `vacation`

#### Scenario: A longer tag holds the same text
- **WHEN** the user renames `travel`, and a transaction holds `travel-insurance`
- **THEN** the system leaves `travel-insurance` unchanged

#### Scenario: The user submits an empty new value
- **WHEN** the user submits an empty new value
- **THEN** the page shows an error, and nothing changes

### Requirement: Delete of a tag
A delete SHALL remove the tag from the rule-assigned tags and the manual tags of
each transaction. The system SHALL clear the field when the tag was the only
tag. The system SHALL leave each rule unchanged, because an edit to a rule is a
separate audited action.

#### Scenario: The tag was the only tag
- **WHEN** the user deletes the only tag of a transaction
- **THEN** that transaction has no tag

#### Scenario: A rule assigns the deleted tag
- **WHEN** the user deletes a tag that a rule assigns
- **THEN** the rule still assigns the tag, and it adds the tag again at the next
  reapplication
