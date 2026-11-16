# iOS Help Specification

## Purpose

The help tab explains the companion app and its relation to the desktop
application. The user can read this guidance inside the app.

## Requirements

### Requirement: In-app help tab
The app SHALL show help as one of its top-level tabs.

#### Scenario: The user opens the help tab
- **WHEN** the user opens the help tab
- **THEN** the app shows the guidance, and the user stays in the app

### Requirement: Explanation of the snapshot-only relation
The help content SHALL explain that the desktop application is the primary tool.
It SHALL also explain that the two apps exchange data only through snapshots,
and never through a shared database file.

#### Scenario: The user reads about sync
- **WHEN** the user reads the help
- **THEN** the help describes snapshot import, snapshot export, and sync from
  the computer with a QR code

### Requirement: Steps for the QR code sync
The help SHALL give the steps for a sync with the QR code. The steps SHALL name
the "Share to phone" control on the Snapshots page of the desktop application
and the "Sync from computer" control of the app. The help SHALL tell the user
that both devices must use the same Wi-Fi network, and that the QR code works
for one download only and expires after 10 minutes.

#### Scenario: The user reads the QR code steps
- **WHEN** the user opens the help tab
- **THEN** the help shows the numbered steps for the QR code sync

### Requirement: Sample data controls
The help tab SHALL hold a control that loads the sample dataset, and a control
that removes it. The help tab SHALL show the load control while the sample
dataset is absent, and the remove control while it is present.

#### Scenario: The user removes the sample data from the help tab
- **WHEN** the sample dataset is present and the user taps "Remove sample data"
- **THEN** the app deletes the sample rows, and the help tab shows the load
  control again

### Requirement: Offline help
The app SHALL show the help content when the device has no network connection.

#### Scenario: The device has no network
- **WHEN** the device has no network
- **THEN** the help tab renders its content
