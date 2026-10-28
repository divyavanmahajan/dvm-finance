# Tag-only Rules Specification

## Purpose

A tag-only rule attaches a cross-cutting label to a transaction, for example
`recurring`, `large-expense`, or `joint-account`. The label applies whatever the
category is, and the rule never competes for the category.

## Requirements

### Requirement: No category from a tag-only rule
A rule with the tag-only flag SHALL hold no category, and it SHALL require at
least one tag. The rule SHALL never write the category or the manual category of
a transaction.

#### Scenario: The form holds a category
- **WHEN** the user saves a rule with the tag-only flag and a category in the
  form
- **THEN** the stored rule holds no category

#### Scenario: The form holds no tag
- **WHEN** the user saves a tag-only rule with no tag
- **THEN** the system rejects the save with a validation error

### Requirement: Second pass for the tag-only rules
The system SHALL apply the tag-only rules in a second pass, after the category
pass assigns the categories.

#### Scenario: Two rules match one transaction
- **WHEN** a category rule and a tag-only rule both match one transaction
- **THEN** the transaction holds the category from the category rule and the
  union of the tags from both rules

### Requirement: Contribution from each matching rule
The tag-only pass SHALL NOT stop at the first match. Each active tag-only rule
that matches a transaction SHALL contribute its tags, whatever its priority is.

#### Scenario: Three rules match one transaction
- **WHEN** three active tag-only rules match one transaction
- **THEN** the transaction holds the tags of all three rules

### Requirement: Tags for a manually categorized transaction
The tag-only pass SHALL run against each transaction, and this includes a
transaction whose categorization source is manual. A manual category can
therefore still receive a cross-cutting tag.

#### Scenario: A rule matches a manual transaction
- **WHEN** a tag-only rule matches a manually categorized transaction
- **THEN** the system merges the tags in and leaves the manual category
  unchanged

### Requirement: Tag merge as a union without duplicates
A merge SHALL split the existing and the incoming values on a comma. It SHALL
append only a tag that is not already present. It SHALL keep the order of the
first appearance. A second application is therefore idempotent.

#### Scenario: The tags overlap
- **WHEN** a transaction holds `recurring,software`, and a matching rule
  contributes `software,saas`
- **THEN** the result is `recurring,software,saas`

#### Scenario: The system applies the same rule twice
- **WHEN** the system applies the same tag-only rule twice
- **THEN** no tag appears twice

### Requirement: Audit of a tag-only change
Take a transaction that only a tag-only rule changed. The change report SHALL
hold the same category before and after, and a different set of tags. The system
SHALL stamp the transaction as updated.

#### Scenario: A rule adds a tag to a categorized transaction
- **WHEN** a tag-only rule adds a tag to a transaction that already has a
  category
- **THEN** the stored report item shows the same category before and after, and
  the difference in the tags

### Requirement: Separate list for the tag-only rules
The rules list SHALL show the tag-only rules in their own tab, apart from the
category rules. The count of each tab SHALL stay visible.

#### Scenario: The user opens the tag-only tab
- **WHEN** the user opens the tag-only tab
- **THEN** the page lists only the tag-only rules, with the same preview and
  history actions as for a category rule
