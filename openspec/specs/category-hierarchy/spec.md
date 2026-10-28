# Category Hierarchy Specification

## Purpose

This capability defines how the system writes and reads a hierarchical category
name. A parent category selects its complete subtree in the filters, the trends,
and the budgets.

## Requirements

### Requirement: Hyphen-separated category names
A hierarchical category SHALL consist of segments that a hyphen joins, for
example `groceries-ah` or `fixed-insurance-life`. The system SHALL store a
category in lower case. The system SHALL read a comma-separated category value
as a list of trimmed, lower-case parts.

#### Scenario: The user enters a mixed-case category
- **WHEN** the user enters the category ` Food, Groceries `
- **THEN** the system stores `food, groceries`

#### Scenario: The user enters a blank category
- **WHEN** the user enters only whitespace as the category
- **THEN** the system stores no category

### Requirement: Subtree matching
A selected category SHALL match that exact category. It SHALL also match each
descendant whose name continues after a hyphen. The comparison ignores the case.

#### Scenario: A parent selects its children
- **WHEN** the user selects `fixed-insurance`
- **THEN** both `fixed-insurance` and `fixed-insurance-life` match

#### Scenario: A partial segment does not match
- **WHEN** the user selects `fixed-ins`
- **THEN** `fixed-insurance` does not match, because the hyphen is the segment
  boundary

### Requirement: Top-level rollup
An aggregation that groups the categories SHALL roll each category up to its
first segment. The aggregation SHALL also expose the exact child categories of
each group, so that a link can reproduce the group.

#### Scenario: Two children in one group
- **WHEN** the data contains `groceries-ah` and `groceries-lidl`
- **THEN** both are children of a `groceries` group, and the group value is
  their sum

#### Scenario: A group with one exact match
- **WHEN** the only value in a group is the name of the parent
- **THEN** the system shows the group as one row and gives it no children

### Requirement: Addressable uncategorized state
The system SHALL accept the pseudo-category `uncategorized` as a selection for
the absence of a category. The system SHALL show the label `Uncategorized` for
that state.

#### Scenario: The user selects the uncategorized state
- **WHEN** the user selects `uncategorized` as the category
- **THEN** only the transactions with a null or empty effective category match
