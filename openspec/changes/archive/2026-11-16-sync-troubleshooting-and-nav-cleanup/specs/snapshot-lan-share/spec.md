## ADDED Requirements

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
