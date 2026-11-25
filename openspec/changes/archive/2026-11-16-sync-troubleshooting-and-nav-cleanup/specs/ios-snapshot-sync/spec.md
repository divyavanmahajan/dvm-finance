## MODIFIED Requirements

### Requirement: Explicit handling of the local-network permission
The app SHALL classify a failed download from the error that the platform
returns. The app SHALL NOT infer a permission problem from the address class
alone. The app SHALL show the local-network permission message only when the
platform reports that the local network is prohibited. That message SHALL hold
a link into the system settings. The other failure messages SHALL NOT hold that
link.

#### Scenario: The user has not granted the permission
- **WHEN** the download fails, and the platform error reports that the local
  network is prohibited
- **THEN** the app explains the local-network permission and offers to open the
  settings

#### Scenario: The computer refuses the connection
- **WHEN** the download to a private network address fails because the
  computer refuses the connection
- **THEN** the app tells the user that the QR code expired or was already used,
  and that the user must make a new QR code on the computer

#### Scenario: The connection to a private address times out
- **WHEN** the download to a private network address times out, or the host is
  unreachable, and the platform does not report a prohibited local network
- **THEN** the app tells the user to put both devices on the same Wi-Fi network
- **AND** the app names a VPN on the phone, a guest network, and the firewall of
  the computer as possible causes

#### Scenario: The public host does not answer
- **WHEN** the download to a public host fails
- **THEN** the app suggests a new QR code and a check of the network

#### Scenario: The user has the permission on and the share expired
- **WHEN** the local-network permission is on, and the scanned share already
  stopped
- **THEN** the app does not show the local-network permission message

### Requirement: No export of sample data
The app SHALL refuse a full export and a delta export while the database holds
the sample dataset. The refusal SHALL tell the user to remove the sample data
first. The fictional rows therefore never reach the desktop database.

#### Scenario: The user exports with sample data present
- **WHEN** the database holds the sample dataset and the user taps an export
  control
- **THEN** the app writes no file, and it tells the user to remove the sample
  data in the import tab or the help tab
