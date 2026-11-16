## MODIFIED Requirements

### Requirement: Steps for the QR code sync
The help SHALL give the steps for a sync with the QR code. The steps SHALL name
the QR icon in the navigation of the desktop application and the "Sync from
computer" control of the app. The help SHALL tell the user that both devices
must use the same Wi-Fi network, and that the QR code works for one download
only and expires after 10 minutes. The help SHALL also give troubleshooting
steps for a failed sync.

#### Scenario: The user reads the QR code steps
- **WHEN** the user opens the help tab
- **THEN** the help shows the numbered steps for the QR code sync

#### Scenario: The user reads the troubleshooting steps
- **WHEN** the user opens the help tab
- **THEN** the help tells the user to make a new QR code, to check the Wi-Fi
  network and a VPN, and to open the QR link in Safari to test the network

### Requirement: Sample data controls
The help tab and the import tab SHALL each hold a control that loads the sample
dataset, and a control that removes it. Each tab SHALL show the load control
while the sample dataset is absent, and the remove control while it is present.

#### Scenario: The user removes the sample data from the help tab
- **WHEN** the sample dataset is present and the user taps "Remove sample data"
- **THEN** the app deletes the sample rows, and the help tab shows the load
  control again

#### Scenario: The user removes the sample data from the import tab
- **WHEN** the sample dataset is present and the user taps "Remove sample data"
  in the import tab
- **THEN** the app deletes the sample rows, shows the count of the removed
  rows, and the import tab shows the load control again

#### Scenario: The user loaded the sample data in another tab
- **WHEN** the user loads the sample data in the transactions tab and then opens
  the import tab
- **THEN** the import tab shows the remove control
