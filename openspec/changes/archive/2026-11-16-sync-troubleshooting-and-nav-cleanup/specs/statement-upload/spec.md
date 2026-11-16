## MODIFIED Requirements

### Requirement: Upload page and endpoint
The system SHALL offer an Import page at `/import`. The Import page SHALL hold
the download sources first and the upload form after them. The system SHALL
also offer an endpoint that accepts one statement file and an optional format
selection.

#### Scenario: The user opens the upload page
- **WHEN** the user opens the Import page
- **THEN** the page shows a file field and the available format choices

#### Scenario: The user uploads a file from the Import page
- **WHEN** the user submits a statement file from the Import page
- **THEN** the Import page shows the import summary, and the user stays on the
  Import page
