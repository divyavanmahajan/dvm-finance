# iOS Manual Categorization Specification

## Purpose

Manual edits let the user correct a transaction on the phone. Without them, the
transactions that the phone imports are a dead end.

## Requirements

### Requirement: Manual edits to the category and the tags
The app SHALL let the user set and clear the manual category and the manual tags
of a transaction. The app SHALL offer pickers that it builds from the categories
and the tags already in use.

#### Scenario: The user sets a category
- **WHEN** the user selects a category for a transaction
- **THEN** that category becomes the effective category of the transaction

#### Scenario: The user clears an override
- **WHEN** the user clears the manual category
- **THEN** the rule-assigned category becomes effective again

### Requirement: Parity with the desktop semantics
A manual edit SHALL set the categorization source of the transaction to manual.
The app SHALL also stamp the transaction as updated. A clear operation SHALL
reset the source only when both manual fields are empty. This behavior is
identical to the desktop application.

#### Scenario: The user clears one of two manual values
- **WHEN** the user clears the manual category, and the manual tags remain
- **THEN** the categorization source stays manual

#### Scenario: The app stamps a manual edit
- **WHEN** the user makes any manual edit
- **THEN** the app stamps the transaction as updated, and a delta export carries
  that transaction

### Requirement: Protection of manual edits from the rules
The category pass on the phone SHALL skip the manually categorized
transactions. The app SHALL NOT write the manual fields. Only a snapshot import
SHALL replace them.

#### Scenario: The rules run after a file import
- **WHEN** the rules run after a file import
- **THEN** the manually categorized transactions keep their manual values

### Requirement: No rule editor on the phone
The app SHALL NOT create, edit, delete, or preview a rule. Rules SHALL arrive
only through a snapshot import.

#### Scenario: The user looks for a rule editor
- **WHEN** the user looks for a rule editor
- **THEN** the app offers no such function, and the rules in effect are the
  rules from the last imported snapshot
