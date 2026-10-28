# Help Guide Specification

## Purpose

The help page gives the user the product documentation inside the running
application. The user can read about the features and the companion app without
a visit to an external site.

## Requirements

### Requirement: In-app help page
The system SHALL serve a help page. The page SHALL render the bundled user guide
and the companion-app section from Markdown into HTML.

#### Scenario: The user opens the help page
- **WHEN** the user opens the help page
- **THEN** the system renders the feature guide and the companion-app section as
  formatted HTML

### Requirement: Packaged help content
The installed package SHALL contain the Markdown source files. The help page
SHALL render its content for an installation from the published package, and not
only from a source checkout.

#### Scenario: The application runs from the published package
- **WHEN** the user runs the application from an installed package
- **THEN** the help page renders its content

### Requirement: Graceful behavior for absent content
If a help document is absent, the system SHALL render that section as empty. The
page SHALL NOT fail.

#### Scenario: One document is absent
- **WHEN** one of the help documents is not present
- **THEN** the page renders with the remaining section
