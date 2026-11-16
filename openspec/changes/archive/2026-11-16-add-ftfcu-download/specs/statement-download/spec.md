# Spec Delta

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
- **THEN** the download page refreshes the status of that source about every 2
  seconds, until the job reaches a final state

## ADDED Requirements

### Requirement: The First Tech job attaches after the login
The First Tech job SHALL NOT attach an automation client to Chrome before the
user logs in. It SHALL find a First Tech tab through the HTTP list of targets.
If no such tab exists, it SHALL open one through the HTTP endpoint for a new
target. It SHALL wait until a tab shows the account overview, for at most 5
minutes. Only then SHALL it attach. At the end it SHALL detach and SHALL keep
the tab of the user open.

#### Scenario: The user is not logged in
- **WHEN** the user starts a First Tech download, and the First Tech tab shows
  the login page
- **THEN** the job waits and does not attach, and the status asks the user to
  log in

#### Scenario: No First Tech tab is open
- **WHEN** the user starts a First Tech download, and no First Tech tab is open
- **THEN** the job opens the account overview in a new tab without an attach

#### Scenario: The login does not occur
- **WHEN** no tab shows the account overview within 5 minutes
- **THEN** the job fails with a login timeout

### Requirement: One OFX file for all First Tech accounts
After the login, the First Tech job SHALL read the token and the account
identifiers from the export form of the page. It SHALL request one OFX file for
all the accounts and the selected range. It SHALL import the file with the
First Tech format. A response that is not OFX SHALL fail the job with a message
that tells the user to log in again. A range with no transactions SHALL end the
job as done with no new transaction.

#### Scenario: The range holds transactions
- **WHEN** the export returns an OFX file with transactions for four accounts
- **THEN** the job imports the file and reports the number of new transactions

#### Scenario: The range holds no transaction
- **WHEN** the export returns an OFX file with no transaction
- **THEN** the job ends as done, and it reports no new transaction

### Requirement: First Tech date range
The First Tech download SHALL take a date range with the default of the other
sources. The system SHALL reject a malformed date or an inverted range with
status 400, before any browser work starts. The job SHALL move the start to two
years before today, because the bank refuses older transactions. It SHALL move
the end back to today.

#### Scenario: The start is too old
- **WHEN** the user asks for a range that starts five years ago
- **THEN** the job starts the range two years before today
