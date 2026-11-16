## MODIFIED Requirements

### Requirement: List of the past exports
The Export page SHALL list the files in the snapshots folder, with the newest
first. Each entry SHALL hold the size and the modification time of the file. The
system SHALL let the user download a listed file again. The system SHALL serve
only the name of a listed export.

#### Scenario: The user clicks a past export
- **WHEN** the user clicks a file from an earlier export
- **THEN** the system returns that file as a download

#### Scenario: The request names another path
- **WHEN** a download request names a file that the list does not hold
- **THEN** the system responds with status 404

## ADDED Requirements

### Requirement: Export page
The system SHALL offer the export, the share, and the import of snapshots on
one page at `/export`. The page title and the navigation label SHALL be
"Export".

#### Scenario: The user opens the Export page
- **WHEN** the user opens `/export`
- **THEN** the page shows the export controls, the "Share to phone" control,
  the snapshot import form, and the list of past exports
