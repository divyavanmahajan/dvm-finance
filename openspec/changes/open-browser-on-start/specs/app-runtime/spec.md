# Spec Delta

## ADDED Requirements

### Requirement: The command opens the browser at the address of the app
The command SHALL open the default browser of the user at the address of the
application, one time for each run of the server. The command SHALL open the
browser only after the server accepts a connection, so that the browser does not
reach a closed port.

#### Scenario: The user starts the server
- **WHEN** the user starts the application with no option that stops it
- **THEN** the command opens the default browser at the address of the
  application, after the server accepts a connection

#### Scenario: The server needs time to start
- **WHEN** the server needs some seconds before it accepts a connection
- **THEN** the command waits for the connection, and the browser therefore
  reaches a server that answers

#### Scenario: The server never accepts a connection
- **WHEN** the server does not accept a connection before the time limit
- **THEN** the command opens no browser, and the server keeps its own behavior

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
browser. The environment variable `DVM_FINANCE_NO_BROWSER` SHALL have the same
effect, for a start without a command line. The option and the variable SHALL
change nothing else.

#### Scenario: The user gives the option
- **WHEN** the user starts the application with `--no-browser`
- **THEN** the command opens no browser, and the server starts as usual

#### Scenario: The environment holds the variable
- **WHEN** the environment holds `DVM_FINANCE_NO_BROWSER` with a value that is
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
