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

### Requirement: Offline help
The app SHALL show the help content when the device has no network connection.

#### Scenario: The device has no network
- **WHEN** the device has no network
- **THEN** the help tab renders its content
