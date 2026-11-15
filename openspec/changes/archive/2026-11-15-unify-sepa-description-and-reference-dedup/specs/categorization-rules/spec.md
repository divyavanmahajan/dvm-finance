# Spec Delta

## ADDED Requirements

### Requirement: Migration of a renamed structured field target
The system SHALL migrate each rule whose field target names a structured key
that this change renames. The migration SHALL run one time, and it SHALL set the
new key. A rule that names an unknown field target matches nothing, so the
system SHALL NOT leave the old key in place.

#### Scenario: A rule targets the old remittance key
- **WHEN** a rule holds the field target `description` with the rule type
  `structured_field`
- **THEN** the migration sets the field target `remittance_info`

#### Scenario: A rule targets the old reference key
- **WHEN** a rule holds the field target `reference`
- **THEN** the migration sets the field target `end_to_end_reference`

#### Scenario: A rule targets the raw description
- **WHEN** a rule holds the field target `description` with the rule type
  `full_description`
- **THEN** the migration changes nothing, because that target names the raw text
  and not a structured key

#### Scenario: An extra condition names an old key
- **WHEN** an extra condition of a rule holds the field target `reference`
- **THEN** the migration sets the field target `end_to_end_reference` on that
  condition

### Requirement: Audit report for the field target migration
The migration SHALL write a rule change report. The report SHALL name each rule
that it changed, and each transaction whose category or tags changed. The
migration SHALL NOT overwrite a manual categorization.

#### Scenario: The migration changes a rule
- **WHEN** the migration changes the field target of a rule
- **THEN** the system stores a rule change report with the rule before the
  change and the rule after the change

#### Scenario: A transaction holds a manual category
- **WHEN** the migration reapplies the rules, and a transaction holds a manual
  category
- **THEN** the category of that transaction does not change
