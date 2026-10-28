# Statement Download Specification

## Purpose

This capability fetches a statement from ABN AMRO, PayPal, Wise, and SEB. It
drives the Chrome browser of the user, so that the user authenticates in person
and the application holds no bank credential.

## Requirements

### Requirement: Use of the Chrome browser of the user
Each download SHALL attach to a Google Chrome browser that already runs, across
its remote debugging endpoint. The system SHALL NOT start a bundled browser. The
download therefore uses the session and the cookies of the user.

#### Scenario: The request names no endpoint
- **WHEN** the user starts a download with no endpoint
- **THEN** the system uses the default local debugging endpoint

#### Scenario: The request names an endpoint
- **WHEN** the user gives a debugging URL on another port
- **THEN** the system uses that endpoint

### Requirement: Launch of Chrome for debugging
The system SHALL offer a one-click launch of Chrome with remote debugging on the
port of the configured endpoint. The launch SHALL use a separate profile
directory, and it SHALL detach Chrome from the application process. If Chrome is
not at the expected location, the system SHALL report that and show the exact
command for a manual launch.

#### Scenario: Chrome is installed
- **WHEN** the user clicks the launch button, and Chrome is installed
- **THEN** Chrome starts with remote debugging on the configured port

#### Scenario: Chrome is absent
- **WHEN** Chrome is not at the expected path
- **THEN** the page reports that and shows the manual launch command

### Requirement: One job for each source
At most one download job SHALL run for each source at a time. A second start for
a source whose job still runs SHALL fail with status 409.

#### Scenario: A job already runs
- **WHEN** an ABN download runs, and the user starts another
- **THEN** the system responds with status 409, and the running job continues

#### Scenario: The job has ended
- **WHEN** a job has ended with success or with failure
- **THEN** the user can start a new job for that source

### Requirement: Job states and progress
A job SHALL move across the states pending, waiting-for-auth, downloading,
importing, and then done or failed. A job SHALL carry a message for the user. A
job SHALL expose its start time, its end time, and its import summary, once the
summary exists.

#### Scenario: The job reaches the login page
- **WHEN** the job reaches the login page of the provider
- **THEN** its state is waiting-for-auth, and its message asks the user to
  authenticate in the attached Chrome window

#### Scenario: The job ends
- **WHEN** a job ends the import
- **THEN** its state is done
- **AND** it carries the total count of the new, the duplicate, the categorized,
  and the uncategorized transactions

### Requirement: Status polling
The system SHALL expose a status fragment for each source. The system SHALL
respond with status 404 for an unknown source. The supported sources are ABN
AMRO, PayPal, Wise, and SEB.

#### Scenario: The source is unknown
- **WHEN** a status request names an unsupported source
- **THEN** the system responds with status 404

#### Scenario: A job runs
- **WHEN** a job runs
- **THEN** the download page refreshes the status of that source about every 2
  seconds, until the job reaches a final state

### Requirement: Automatic import of a downloaded statement
The system SHALL send each downloaded file through the normal import pipeline.
The duplicate removal and the rule application therefore work exactly as for a
manual upload. The system SHALL total the results of each file into one job
summary.

#### Scenario: One run covers three accounts
- **WHEN** a run downloads a statement for three accounts
- **THEN** the system imports all three files and totals their counts into the
  job summary

#### Scenario: The system cannot parse one file
- **WHEN** the system cannot parse one downloaded file
- **THEN** it reports that file, and the run continues with the other files

### Requirement: Default date range from the last successful download
The system SHALL record the end of the last successful range for each source.
The system SHALL start a new default range on the day after that end, and clamp
the start to today. Without an earlier run, the default range SHALL cover the
last 180 days. The system SHALL also accept a range from the user.

#### Scenario: An earlier run exists
- **WHEN** the last successful ABN run ended on the 10th
- **THEN** the form defaults to a start on the 11th

#### Scenario: The earlier run reached today
- **WHEN** the last successful run ended today or later
- **THEN** the default range starts today, and it does not invert

#### Scenario: No earlier run exists
- **WHEN** no successful run exists for a source
- **THEN** the default range covers the last 180 days

### Requirement: No date range for SEB
The SEB download SHALL take no date range. Its export returns the recent history
of the account, and the import skips each duplicate.

#### Scenario: The user starts an SEB download
- **WHEN** the user starts an SEB download
- **THEN** the system needs no date
- **AND** it imports the returned history and skips each duplicate

### Requirement: Rejection of a malformed date
The system SHALL reject a date that is not a valid ISO date with status 400,
before any browser work starts.

#### Scenario: The date is malformed
- **WHEN** the user starts a download with a malformed date
- **THEN** the system responds with status 400 and names the expected format

### Requirement: Actionable messages for a connection failure
If the system cannot reach the debugging endpoint, the message SHALL hold the
exact Chrome launch command. If a program other than a full Chrome listens on the
port, the message SHALL say so. It SHALL also suggest another port with the
matching command and URL. If the browser automation package is absent, the message SHALL
hold the command for a reinstallation.

#### Scenario: No program listens
- **WHEN** no Chrome listens on the endpoint
- **THEN** the message holds the launch command for that port

#### Scenario: Another program holds the port
- **WHEN** the endpoint answers, but it is not a full Chrome browser
- **THEN** the message explains the conflict on the port and suggests the next
  port with its command and URL

#### Scenario: The automation package is absent
- **WHEN** the browser automation package is not installed
- **THEN** the message holds the command for a reinstallation with that package,
  and not an import error
