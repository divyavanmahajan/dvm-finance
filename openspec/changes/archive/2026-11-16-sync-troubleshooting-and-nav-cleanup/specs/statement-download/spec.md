## MODIFIED Requirements

### Requirement: Status polling
The system SHALL expose a status fragment for each source. The system SHALL
respond with status 404 for an unknown source. The supported sources are ABN
AMRO, PayPal, Wise, SEB, and First Tech.

#### Scenario: The source is unknown
- **WHEN** a status request names an unsupported source
- **THEN** the system responds with status 404

#### Scenario: A job runs
- **WHEN** a job runs
- **THEN** the Import page refreshes the status of that source about every 2
  seconds, until the job reaches a final state
