# Manual Categorization Specification

## Purpose

This capability lets the user override the category and the tags of a
transaction by hand. Those edits survive each reapplication of the rules. A
correction to one transaction therefore stays.

## Requirements

### Requirement: Precedence of the manual values
The system SHALL take the manual category of a transaction as its effective
category, if the manual category is set. The system SHALL otherwise take the
rule-assigned category. The same precedence applies to the tags.

#### Scenario: A transaction has both categories
- **WHEN** a transaction has a rule-assigned category and a different manual
  category
- **THEN** each view shows the manual category

#### Scenario: The manual value is blank
- **WHEN** the manual category of a transaction is empty
- **THEN** the rule-assigned category is the effective category

### Requirement: Protection of the manual edits from the rules
A reapplication of the rules SHALL NOT write the manual category or the manual
tags of a transaction, in any circumstance. Only an explicit snapshot import
SHALL replace them.

#### Scenario: The system applies the rules again
- **WHEN** the system applies the rules again over a transaction with a manual
  category
- **THEN** the manual category and the manual tags stay unchanged

### Requirement: A manual category for one transaction
The system SHALL accept a manual category for one transaction. The system SHALL
normalize the value, set the categorization source of the transaction to manual,
and stamp the transaction as updated.

#### Scenario: The user sets a category on a row
- **WHEN** the user sets a manual category on a transaction row
- **THEN** the system stores the normalized value, sets the categorization
  source to manual, and stamps the update time
- **AND** the system returns the refreshed row

#### Scenario: The request names an unknown transaction
- **WHEN** the request names a transaction id that does not exist
- **THEN** the system responds with status 404

### Requirement: Manual tags for one transaction
The system SHALL accept a comma-separated list of manual tags for one
transaction. The system SHALL trim each entry and drop a blank entry. It SHALL
set the categorization source to manual and stamp the transaction as updated. An
empty list SHALL clear the manual tags.

#### Scenario: The user submits untidy tags
- **WHEN** the user submits ` travel , , food `
- **THEN** the system stores the manual tags `travel, food`

### Requirement: Additive bulk tags
A bulk tag action SHALL union the new tags into the existing effective tags of
each selected transaction. The union removes the duplicates and keeps the order.
The action SHALL NOT drop a tag that a transaction already holds. The system
SHALL write the result to the manual tags and set the categorization source to
manual.

#### Scenario: A transaction already holds a tag
- **WHEN** a transaction already holds `recurring`, and the user adds
  `subscription` in bulk
- **THEN** its manual tags become `recurring, subscription`

#### Scenario: The request is incomplete
- **WHEN** the request holds no transaction id, a value that is not a list, or
  no tag
- **THEN** the system responds with status 400, and it writes nothing

### Requirement: Clear of a manual override
A clear of the manual category or the manual tags SHALL restore the
rule-assigned value as the effective value. The system SHALL reset the
categorization source only when it was manual and no other manual value remains
on that transaction.

#### Scenario: Manual tags remain after the clear
- **WHEN** the user clears the manual category of a transaction that still holds
  manual tags
- **THEN** the categorization source stays manual

#### Scenario: The user clears the last manual value
- **WHEN** the user clears the manual category, and no manual tag remains
- **THEN** the system resets the categorization source, and the next
  reapplication of the rules can categorize the transaction again

### Requirement: A visible mark for a manual edit
The system SHALL report a transaction as manually categorized when its
categorization source is manual, or when it holds a manual category. The table
can therefore mark the row.

#### Scenario: A transaction has a manual category
- **WHEN** a transaction has a manual category
- **THEN** the system flags its row as manually categorized
