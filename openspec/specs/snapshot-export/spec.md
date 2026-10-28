# Snapshot Export Specification

## Purpose

An export packs the dataset into one portable file. The user can give the file
to one other person, or to the iOS companion app. This is the only path between
two installations.

## Requirements

### Requirement: Snapshot format
The system SHALL write a snapshot as one gzipped JSON file. The file SHALL hold
a header with the schema version 1, an export time, and the identifier of the
machine. The file SHALL also hold four arrays: the transactions, the rules, the
budgets, and the rule-change reports.

#### Scenario: The system exports a snapshot
- **WHEN** the system exports a snapshot
- **THEN** the file decompresses into an object with that header and all four
  arrays

### Requirement: Exported content
The export SHALL hold each stored column of a transaction, and this includes the
manual fields and the categorization source. It SHALL hold each rule with its
UUID and its ordered conditions. It SHALL hold each budget without its local id.
It SHALL hold each rule-change report with its items. It SHALL write a date and
a time as an ISO-8601 string, and an amount as a decimal string.

#### Scenario: A transaction has a manual category
- **WHEN** a transaction has a manual category
- **THEN** the exported file holds that manual value

#### Scenario: A rule has two conditions
- **WHEN** a rule has two conditions
- **THEN** the exported rule holds both conditions, in order

### Requirement: Machine identity
Each installation SHALL hold a stable identifier in its data directory. The
system SHALL create the identifier at the first use. The system SHALL write the
identifier into each snapshot that it exports.

#### Scenario: The system exports two snapshots
- **WHEN** the system exports two snapshots from the same installation
- **THEN** both hold the same machine identifier

### Requirement: Full export
The system SHALL export a full snapshot on request. The system SHALL write the
file into the snapshots folder of the data directory with a timestamped name.
The system SHALL offer the file as a download.

#### Scenario: The user exports a snapshot
- **WHEN** the user exports a snapshot
- **THEN** the system writes the file under the snapshots folder and returns it
  as a download

#### Scenario: Two exports fall in the same second
- **WHEN** a second export would use an existing file name
- **THEN** the system adds a suffix, and it does not overwrite the earlier file

### Requirement: Delta export
The system SHALL export a delta snapshot. The delta SHALL hold only the
transactions that changed at the boundary or after it. The system SHALL omit a
transaction that it never stamped. The header SHALL mark the file as a delta and
record the boundary. The export SHALL still hold the complete rules, budgets,
and reports. A delta is therefore a snapshot with fewer transactions, and the
import path is identical.

#### Scenario: The user exports a delta
- **WHEN** the user exports a delta with a boundary of yesterday
- **THEN** the file holds only the transactions with a stamp of yesterday or
  later

#### Scenario: A transaction has no stamp
- **WHEN** a transaction has no change stamp
- **THEN** the delta omits that transaction

#### Scenario: The file describes itself
- **WHEN** the system exports a delta
- **THEN** its header marks the file as a delta and records the boundary

### Requirement: Default boundary for a delta
The system SHALL remember the time of the last delta export. The system SHALL
default the next boundary to that time, so that a delta covers each change since
the previous one. Without a previous delta, the boundary SHALL cover each
transaction with a change stamp. The system SHALL also accept a boundary from
the user.

#### Scenario: The user exports two deltas in turn
- **WHEN** the user exports a delta, and then exports another with no boundary
- **THEN** the second delta holds only the changes since the first one

#### Scenario: The system cannot parse the boundary
- **WHEN** the system cannot parse the boundary from the form
- **THEN** the system uses the stored default, and the request does not fail

### Requirement: List of the past exports
The snapshots page SHALL list the files in the snapshots folder, with the newest
first. Each entry SHALL hold the size and the modification time of the file. The
system SHALL let the user download a listed file again. The system SHALL serve
only the name of a listed export.

#### Scenario: The user clicks a past export
- **WHEN** the user clicks a file from an earlier export
- **THEN** the system returns that file as a download

#### Scenario: The request names another path
- **WHEN** a download request names a file that the list does not hold
- **THEN** the system responds with status 404
