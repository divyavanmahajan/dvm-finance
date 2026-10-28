# Spec Delta

## ADDED Requirements

### Requirement: The prefix of each environment variable
Each environment variable of the application SHALL use the prefix
`DVM_FINANCE_`, which is the name of the package and of the command. The
variables are `DVM_FINANCE_DATA_DIR` for the data directory,
`DVM_FINANCE_LOG_ENV` for the logging environment, and `DVM_FINANCE_NO_BROWSER`
for the browser at the start.

#### Scenario: The user sets the data directory
- **WHEN** the user sets `DVM_FINANCE_DATA_DIR` and gives no option
- **THEN** the application uses that directory

#### Scenario: The user sets the logging environment
- **WHEN** the user sets `DVM_FINANCE_LOG_ENV` to `production`
- **THEN** the application writes its log in the production form

#### Scenario: The user stops the browser
- **WHEN** the user sets `DVM_FINANCE_NO_BROWSER` to a value that is not empty
- **THEN** the command opens no browser

### Requirement: The application still reads the old name
The application SHALL also read the name with the prefix `ABN_COMBINED_`, which
the rename of the project left behind. The new name SHALL win when both names
hold a value. A later major version removes the old name, and this behavior is
therefore temporary.

#### Scenario: Only the old name holds a value
- **WHEN** the environment holds `ABN_COMBINED_DATA_DIR` and not the new name
- **THEN** the application uses that directory, exactly as before the rename

#### Scenario: Both names hold a value
- **WHEN** the environment holds both names with different values
- **THEN** the application uses the value of the new name

### Requirement: The application warns about an old name
The application SHALL write one warning for each old name from which it reads a
value. The warning SHALL name the old name and the new name. The application
SHALL write no warning when the environment holds the new name only, and none
when it holds neither name.

#### Scenario: The user starts the application with an old name
- **WHEN** the application reads a value from `ABN_COMBINED_DATA_DIR`
- **THEN** the application writes a warning that names
  `ABN_COMBINED_DATA_DIR` and `DVM_FINANCE_DATA_DIR`

#### Scenario: The user starts the application with the new name
- **WHEN** the environment holds the new name only
- **THEN** the application writes no warning about a name

#### Scenario: The environment holds both names
- **WHEN** the environment holds both names
- **THEN** the application writes the warning, because the old name is still
  set and the user must remove it
