## ADDED Requirements

### Requirement: The iOS SEB import without rates
The iOS SEB parser SHALL refuse the file when it cannot get an ECB rate for
each transaction. The import SHALL write no row. The app SHALL tell the user
that the ECB rates are not available and to try again later.

#### Scenario: The iPhone has no network connection
- **WHEN** the user imports an SEB file, and the app cannot fetch the ECB rates
- **THEN** the app shows the message and writes no row

### Requirement: The iOS id of an SEB transaction
The iOS app SHALL give an SEB transaction the SEB voucher key, the same id as
the desktop app. A database migration SHALL change the id of each stored SEB
transaction to that key, and each reference to it. The migration SHALL keep
each other field of the row.

#### Scenario: The same file on the two apps
- **WHEN** the user imports one SEB file on the desktop and on the iPhone
- **THEN** each transaction has the same id in the two apps

#### Scenario: The app updates to this version
- **WHEN** the iOS database holds SEB rows with the old ids, and the app starts
  after the update
- **THEN** each SEB row has the new id, and its manual category stays the same
