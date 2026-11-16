## MODIFIED Requirements

### Requirement: Import report
Each import SHALL store a record. The record SHALL hold the identifier of the
source machine and the schema version. It SHALL hold the count of the inserted,
updated, and unchanged rows for each entity. It SHALL hold the recorded
overwrites. It SHALL
also note a delta file and its boundary. The import SHALL also store a change
report of the change to the effective category and tags of each transaction.

#### Scenario: An import ends
- **WHEN** an import ends
- **THEN** the system returns the user to the Export page, which shows the
  counts and the overwrites of that import

#### Scenario: The file was a delta
- **WHEN** the user imports a delta snapshot
- **THEN** the import record notes the delta and the boundary that it covered

#### Scenario: The user opens the snapshots page
- **WHEN** the user opens the Export page
- **THEN** the page lists the most recent imports, with the newest first
