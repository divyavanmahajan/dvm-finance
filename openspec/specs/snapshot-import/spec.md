# Snapshot Import Specification

## Purpose

An import merges a snapshot from another installation into the local dataset.
The source can be the machine of a partner or the iOS companion. The incoming
data wins, and the system records each value that it replaced.

## Requirements

### Requirement: Validation before any write
The system SHALL validate an uploaded file before it makes any change. The
system SHALL reject a file with a clear message, and it SHALL write nothing, in
four cases. They are a corrupt gzip stream, corrupt JSON, an absent header, a
schema version that the application does not support, and an absent entity
array.

#### Scenario: The file is corrupt
- **WHEN** the user uploads a file that is not a valid gzip stream
- **THEN** the page reports the problem with status 400, and the system imports
  nothing

#### Scenario: The schema version differs
- **WHEN** the schema version of the snapshot differs from the supported version
- **THEN** the message names both versions

### Requirement: Backup before the merge
The system SHALL copy the database file to a timestamped backup beside it,
before the merge starts.

#### Scenario: An import starts
- **WHEN** an import starts
- **THEN** a timestamped copy of the database file exists before the system
  changes any row

### Requirement: One transaction for the merge
The system SHALL run the complete merge, its import record, and its change
report in one database transaction. A failure therefore leaves the database
exactly as it was.

#### Scenario: The merge fails part way through
- **WHEN** the merge fails part way through
- **THEN** the system rolls each change back, and the database is unchanged

### Requirement: Incoming values win on a collision
On an identity collision, the values from the snapshot SHALL replace the local
values. This includes a manual category, manual tags, and a complete rule
definition. This is the only path that may overwrite a manual edit, and it SHALL
always record what it replaced.

#### Scenario: The local transaction holds a manual category
- **WHEN** an incoming transaction differs from a local transaction that holds a
  manual category
- **THEN** the incoming values win, and the system records the overwrite for
  each field

#### Scenario: The rows are identical
- **WHEN** an incoming row is identical to the local row
- **THEN** the system counts the row as unchanged and writes nothing

### Requirement: No delete of a local row
The system SHALL leave a local row that the snapshot does not hold. A delta
snapshot can therefore never remove data.

#### Scenario: The user imports a delta
- **WHEN** the user imports a delta snapshot with three transactions
- **THEN** each other local transaction remains

### Requirement: Entity identity
The system SHALL match a transaction by its deterministic id, and a rule by its
UUID. It SHALL match a budget by the category, the period, and the validity
start. It SHALL then match a budget by the category and the period, which are
unique together. It SHALL match a rule-change report by its creation time, its
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

### Requirement: Remap of the rule references
A transaction records its rule by a local id. The system SHALL remap each
incoming categorization source to the id of the matching local rule, which it
finds by the UUID.

#### Scenario: The incoming id differs from the local id
- **WHEN** an incoming transaction names rule id 5, and the UUID of that rule is
  local rule 12
- **THEN** the stored categorization source becomes 12

### Requirement: No reapplication of the rules after an import
The system SHALL NOT apply the rules again after an import, because the
categorization state in the snapshot is authoritative.

#### Scenario: The local rules disagree with the snapshot
- **WHEN** the local rules would not reproduce the category of an imported
  transaction
- **THEN** the system keeps the imported category

### Requirement: Import report
Each import SHALL store a record. The record SHALL hold the identifier of the
source machine and the schema version. It SHALL hold the count of the inserted,
updated, and unchanged rows for each entity. It SHALL hold the recorded
overwrites. It SHALL
also note a delta file and its boundary. The import SHALL also store a change
report of the change to the effective category and tags of each transaction.

#### Scenario: An import ends
- **WHEN** an import ends
- **THEN** the system returns the user to the snapshots page, which shows the
  counts and the overwrites of that import

#### Scenario: The file was a delta
- **WHEN** the user imports a delta snapshot
- **THEN** the import record notes the delta and the boundary that it covered

#### Scenario: The user opens the snapshots page
- **WHEN** the user opens the snapshots page
- **THEN** the page lists the most recent imports, with the newest first
