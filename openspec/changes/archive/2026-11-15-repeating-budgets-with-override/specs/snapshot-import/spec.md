# Spec Delta

## MODIFIED Requirements

### Requirement: Entity identity
The system SHALL match a transaction by its deterministic id, and a rule by its
UUID. It SHALL match a budget by the category, the period, and the validity
start. It SHALL match a rule-change report by its creation time, its
action, and its rule UUID. A second import therefore does not duplicate the audit trail.

#### Scenario: A rule comes from another machine
- **WHEN** the user imports a rule that another machine created with a different
  local id
- **THEN** the system matches the rule by its UUID and updates it, and it
  creates no duplicate

#### Scenario: The user imports the same snapshot twice
- **WHEN** the user imports the same snapshot twice
- **THEN** the second import reports each row as unchanged, and it adds no
  duplicate report

#### Scenario: Two budgets for one category arrive
- **WHEN** the snapshot holds a monthly `groceries` budget from July to October
  and one from November with no end, and the local data holds the first one
- **THEN** the system updates the first budget and inserts the second one

### Requirement: No delete of a local row
The system SHALL leave a local row that the snapshot does not hold. A delta
snapshot can therefore never remove data. The only exception is a local budget
that an incoming budget of the same category and period overlaps. The incoming
budget replaces it, and the merge report names it.

#### Scenario: The user imports a delta
- **WHEN** the user imports a delta snapshot with three transactions
- **THEN** each other local transaction remains

#### Scenario: An incoming budget overlaps a local budget
- **WHEN** the user imports a snapshot with a monthly `groceries` budget from
  August, and the local data holds a monthly `groceries` budget from July with
  no end
- **THEN** the system replaces the local budget, the merge report names it, and
  each other local row remains

## ADDED Requirements

### Requirement: Overlap of an incoming budget
When an incoming budget does not match a local budget, but its range overlaps a
local budget of the same category and period, the incoming budget SHALL win.
The system SHALL delete each such local budget, insert the incoming budget, and
record each deleted budget in the merge report.

#### Scenario: The partner changed the start of a budget
- **WHEN** the local data holds a monthly `groceries` budget from July with no
  end, and the snapshot holds a monthly `groceries` budget from August with no
  end
- **THEN** the system deletes the local budget, inserts the incoming budget, and
  the merge report names the deleted budget
