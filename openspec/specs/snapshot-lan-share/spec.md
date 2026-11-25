# Snapshot LAN Share Specification

## Purpose

This capability gives a snapshot to a phone on the same network through a QR
code. The user moves no file by hand, and nothing stays reachable on the network
afterwards.

## Requirements

### Requirement: One-shot share of a new snapshot
A start action SHALL export a new full snapshot. The system SHALL serve that
file on the local network at a random port, behind a random single-use token
path. The system SHALL show the URL as a QR code with its expiry time.

#### Scenario: The user starts a share
- **WHEN** the user starts a share
- **THEN** the system exports a new snapshot and shows a QR code that holds its
  one-time URL

### Requirement: Shutdown after one download
The share SHALL accept exactly one successful download. The system SHALL then
stop the server, and the file is no longer reachable.

#### Scenario: The phone has downloaded the snapshot
- **WHEN** the phone has downloaded the snapshot
- **THEN** the server refuses a second request to the same URL, and the system
  stops the server

### Requirement: Expiry of a share
A share SHALL expire 10 minutes after its start, if no download occurs. The
system SHALL then stop the server.

#### Scenario: Nobody uses the share
- **WHEN** 10 minutes pass without a download
- **THEN** the share is no longer active, and the system stops the server

### Requirement: Only the token path
The share server SHALL serve only the exact token path. It SHALL respond with
status 404 to each other path, and it SHALL give no reason.

#### Scenario: A request holds another path
- **WHEN** a request arrives for any other path
- **THEN** the server responds with status 404

### Requirement: One active share
A new share SHALL stop a previous one. The system SHALL also let the user stop
the active share.

#### Scenario: The user starts a second share
- **WHEN** the user starts a second share while one is active
- **THEN** the system stops the first one, and only the new URL works

#### Scenario: The user stops the share
- **WHEN** the user stops the share
- **THEN** the system stops the server and clears the QR code

### Requirement: A local-only application
The network SHALL reach no surface other than the temporary share server. The
application itself SHALL continue to listen on the loopback address.

#### Scenario: A share is active
- **WHEN** a share is active
- **THEN** its URL names the network address of the machine, and the application
  itself stays on the loopback address

### Requirement: Share from the navigation
The QR icon in the navigation SHALL open the Export page with the query
`share=1`. The page SHALL then start a new share at once and show its QR code.
The page SHALL start the share with the same POST action as the "Share to
phone" button. A GET request alone SHALL NOT start a share. After the page
starts the share, it SHALL remove `share=1` from the address bar.

#### Scenario: The user clicks the QR icon
- **WHEN** the user clicks the QR icon on any page
- **THEN** the Export page opens and shows a new QR code without a second click

#### Scenario: A client fetches the URL without a page script
- **WHEN** a client sends only a GET request for `/export?share=1`
- **THEN** the system returns the page and starts no share

#### Scenario: The user reloads the page
- **WHEN** the user reloads the Export page after the QR icon opened it
- **THEN** the page starts no new share, because the address no longer holds
  `share=1`
