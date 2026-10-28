# iOS Snapshot Sync Specification

## Purpose

This capability moves data between the computer and the phone through snapshot
files. The user can use a file, the share sheet, or the QR code that the desktop
application shows. This is the only path between the two apps.

## Requirements

### Requirement: Import of a snapshot file
The app SHALL import a gzipped-JSON snapshot that the user selects through the
file picker. The app SHALL use the same validation and the same database backup before the
import as the desktop application. It SHALL use the same single-transaction
merge, where the incoming values win. It SHALL keep the same audit trail.

#### Scenario: The file is valid
- **WHEN** the user imports a snapshot from the desktop application
- **THEN** the app merges its transactions, rules, budgets, and reports, and it
  stores an import record

#### Scenario: The file is invalid
- **WHEN** the gzip stream or the JSON is corrupt, or the app does not support
  the schema version
- **THEN** the app reports a typed error, and it writes nothing

#### Scenario: An import ends
- **WHEN** an import ends
- **THEN** the app keeps the imported categorization as authoritative, and it
  does not apply the rules again

### Requirement: Export of a snapshot
The app SHALL export a full snapshot and offer it through the system share
sheet. A transaction that the phone imported can therefore reach the computer.

#### Scenario: The user exports a snapshot
- **WHEN** the user exports a snapshot
- **THEN** the app offers a timestamped gzipped-JSON file through the share sheet

### Requirement: Export of a delta
The app SHALL export a delta snapshot with only the transactions that changed
after a selected boundary. The default boundary is the stored last-delta marker,
if one exists.

#### Scenario: A previous delta exists
- **WHEN** the app exported a delta before, and the user asks for another
- **THEN** the default boundary is the time of the previous delta

### Requirement: Fidelity of a round trip
A round trip from the desktop application to the phone and back SHALL lose no
exported field. The app SHALL write a date as an ISO string. It SHALL write an
amount as a decimal string with exactly two decimal places.

#### Scenario: The app exports an amount
- **WHEN** the app exports an amount of -12.3
- **THEN** the file holds exactly two decimal places

### Requirement: Sync from the computer with a QR code
The app SHALL let the user scan the QR code that the desktop application shows.
The app SHALL then download that snapshot and run the same import as the file
picker. The app SHALL end on the same summary screen.

#### Scenario: The user scans an active share
- **WHEN** the user scans the QR code of an active share on the same network
- **THEN** the app downloads and imports the snapshot, and it shows the import
  summary

#### Scenario: The share is no longer available
- **WHEN** the scanned share already served its download, or it expired
- **THEN** the app reports that the share was already in use or has expired

### Requirement: Validation of a scanned payload
The app SHALL accept only an absolute HTTP or HTTPS URL with a host from a
scanned code. The app SHALL refuse each other payload with a readable message.

#### Scenario: The code holds arbitrary text
- **WHEN** the user scans a QR code that holds arbitrary text
- **THEN** the app refuses the payload with an explanation, and it makes no
  request

### Requirement: Explicit handling of the local-network permission
The platform gates local-network access behind a permission that no API can
read. The app SHALL therefore report a failure to a private, link-local, or loopback
address as a problem with the local-network permission. The report SHALL hold a
link into the system settings. The app SHALL report a failure to a public host
as an unreachable server.

#### Scenario: The user has not granted the permission
- **WHEN** the download to a private network address fails
- **THEN** the app explains the local-network permission and offers to open the
  settings

#### Scenario: The public host does not answer
- **WHEN** the download to a public host fails
- **THEN** the app suggests a new QR code and a check of the network

### Requirement: Plain HTTP only for the local network
The app SHALL permit plain HTTP only for local networking. The app SHALL NOT
relax the transport security for the internet.

#### Scenario: The app downloads from a LAN address
- **WHEN** the app downloads a snapshot across plain HTTP from a LAN address
- **THEN** the request succeeds, and the app still forbids an arbitrary plain
  HTTP load
