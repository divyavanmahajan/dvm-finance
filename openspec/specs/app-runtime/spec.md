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

### Requirement: The command opens the browser at the address of the app
The command SHALL open the default browser of the user at the address of the
application, one time for each run of the server. The command SHALL open the
browser only after this application answers at the address, so that the browser
reaches neither a closed port nor another program that holds the port.

#### Scenario: The user starts the server
- **WHEN** the user starts the application with no option that stops it
- **THEN** the command opens the default browser at the address of the
  application, after the server accepts a connection

#### Scenario: The server needs time to start
- **WHEN** the server needs some seconds before it answers
- **THEN** the command waits for the answer, and the browser therefore reaches
  a server that answers

#### Scenario: The server never answers
- **WHEN** this application does not answer before the time limit
- **THEN** the command opens no browser, and the server keeps its own behavior

#### Scenario: Another program answers at the address
- **WHEN** another program holds the port and answers a request
- **THEN** the command opens no browser, because the answer does not identify
  this application

### Requirement: The address for the browser is an address a browser can open
The command SHALL open the loopback address when the bind host is `0.0.0.0`,
because `0.0.0.0` is not an address that a browser can open. The command SHALL
otherwise open the bind host. The command SHALL use the port of the server.

#### Scenario: The application binds to each interface
- **WHEN** the user starts the application with the host `0.0.0.0`
- **THEN** the command opens the address `127.0.0.1` with the port of the server

#### Scenario: The application binds to the loopback address
- **WHEN** the user starts the application with the default host
- **THEN** the command opens that host with the port of the server

### Requirement: The user can stop the command from opening a browser
The command SHALL accept the option `--no-browser`, and it SHALL then open no
browser. The environment variable `ABN_COMBINED_NO_BROWSER` SHALL have the same
effect, for a start without a command line. The option and the variable SHALL
change nothing else.

#### Scenario: The user gives the option
- **WHEN** the user starts the application with `--no-browser`
- **THEN** the command opens no browser, and the server starts as usual

#### Scenario: The environment holds the variable
- **WHEN** the environment holds `ABN_COMBINED_NO_BROWSER` with a value that is
  not empty
- **THEN** the command opens no browser, and the server starts as usual

### Requirement: A browser failure does not stop the server
The command SHALL write a message when it cannot open a browser, for example on
a machine with no graphical session. The server SHALL continue to run, and the
exit status SHALL NOT change.

#### Scenario: The machine has no browser
- **WHEN** the command cannot open a browser
- **THEN** the message names the address, so that the user can open it by hand
- **AND** the server continues to serve

### Requirement: The command opens no browser without a server
The command SHALL open no browser for a run that does not serve the application.
The subcommand `migrate-legacy` therefore opens no browser. A start that fails,
for example on an occupied port or an unwritable data directory, SHALL also open
no browser.

#### Scenario: The user runs the legacy migration
- **WHEN** the user runs the subcommand `migrate-legacy`
- **THEN** the command opens no browser

#### Scenario: Another program holds the port
- **WHEN** the port is already in use
- **THEN** the command opens no browser, and it keeps the message and the
  non-zero exit status for an occupied port
