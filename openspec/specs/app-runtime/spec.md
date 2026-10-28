# Application Runtime Specification

## Purpose

This capability defines how the application starts, where it keeps its data, how
the user reaches it, and how the system keeps the schema current. These are the
ground rules for each other capability.

## Requirements

### Requirement: A local-only default
The application SHALL bind to the loopback address on port 8000 by default. The
application has no authentication layer. The system SHALL therefore never widen
the bind address, unless the user gives a host.

#### Scenario: The user starts the application with no option
- **WHEN** the user starts the application with no option
- **THEN** the application listens on the loopback address at port 8000
- **AND** it prints the URL and the data directory in use

#### Scenario: The user gives a host
- **WHEN** the user gives a host
- **THEN** the application uses that host

### Requirement: Resolution of the data directory
The command-line option SHALL take precedence over the environment variable, and
the environment variable SHALL take precedence over the per-user data directory
of the platform. The database, the stored statements, and the snapshots SHALL
each live under the resolved directory.

#### Scenario: The user sets both the option and the variable
- **WHEN** the user sets both the option and the environment variable
- **THEN** the application uses the directory from the option

#### Scenario: The user sets neither
- **WHEN** the user sets neither
- **THEN** the application uses the per-user data directory of the platform

### Requirement: Preparation and check of the data directory
At startup the application SHALL create the data directory and its statements
and snapshots subdirectories, if they are absent. The application SHALL verify
that it can write to the directory. For a directory that it cannot write to, the
application SHALL print a clear message. The message SHALL name the directory
and the options for another location. The application SHALL then exit with a
non-zero status.

#### Scenario: The directory is not writable
- **WHEN** the application cannot write to the resolved data directory
- **THEN** the application reports that, names the option and the environment
  variable, and exits with a non-zero status

### Requirement: Schema migration at startup
At startup the application SHALL bring the database schema to the most recent
migration. Each schema change SHALL come from a migration, and not from a change
at run time.

#### Scenario: The database comes from an earlier version
- **WHEN** the application starts against a database from an earlier version
- **THEN** the application applies the open migrations before it serves a
  request

### Requirement: Health endpoint
The application SHALL expose a health endpoint. The endpoint SHALL report the
status and the data directory in use.

#### Scenario: A client requests the health endpoint
- **WHEN** a client requests the health endpoint
- **THEN** the endpoint reports an ok status and the data directory

### Requirement: Navigation tabs
The application SHALL show a fixed set of navigation tabs. They are
Transactions, Trends, Rules, Tags, Budgets, Cash Flow, Download, Upload, Cash,
Snapshots, and Help. The application SHALL mark the current tab as active, and
it SHALL keep each label on one line. For a tab with no implementation, the
application SHALL render a placeholder, and the page SHALL NOT fail.

#### Scenario: A page renders
- **WHEN** any page renders
- **THEN** the navigation marks the tab of that page as active

#### Scenario: The user opens the Cash tab
- **WHEN** the user opens the Cash tab
- **THEN** the application shows the form that adds a hand-entered transaction

#### Scenario: The order of the tabs keeps the two similar names apart
- **WHEN** the navigation renders
- **THEN** the Cash tab stands beside Download and Upload, which are the other
  tabs for the entry of data, and not beside Cash Flow, which has a similar
  name and another purpose

### Requirement: Clear message for an occupied port
For an occupied port, the application SHALL report that, suggest another port,
and exit with a non-zero status. The application SHALL NOT raise an unhandled
error.

#### Scenario: The port is in use
- **WHEN** the port is already in use
- **THEN** the message names the port and the option for a change
- **AND** the exit status is non-zero

### Requirement: Distribution and run
The published package SHALL install the application and run it as one command,
with no separate frontend build step. The package SHALL hold the migration tree,
so that a packaged installation can migrate at startup.

#### Scenario: The user runs the published package
- **WHEN** the user starts the application directly from the published package
- **THEN** the application starts, migrates its database, and serves the UI
- **AND** it needs no build step and no bundled browser

### Requirement: Responsive behavior at scale
The transactions view and each aggregation SHALL stay responsive with at least
50,000 transactions. A filter SHALL use indexed queries and pagination on the
server. The trends, the cash flow, and the budget actuals SHALL sum in the
database with grouped queries, and not across rows in the application code.

#### Scenario: The database holds 50,000 transactions
- **WHEN** the database holds 50,000 transactions, and a client requests a
  filtered page
- **THEN** the system fetches only the rows of that page, and the view renders
  without a noticeable wait

#### Scenario: The system computes an aggregation
- **WHEN** the system computes the trends, the cash flow, or the budget actuals
  across that dataset
- **THEN** the sums come from grouped database queries, and the system does not
  load the transactions into the application code

### Requirement: Bounded time for a reapplication
A full reapplication of the rules, together with its change report, SHALL end
inside 10 seconds across 50,000 transactions.

#### Scenario: Recategorize-all runs at scale
- **WHEN** recategorize-all runs against 50,000 transactions
- **THEN** it ends and stores its report inside 10 seconds
