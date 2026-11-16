# sample-data Specification

## Purpose
Lets a new user of the web application load a fictional dataset to try each
page, and remove that dataset later without a change to the real data.

## Requirements

### Requirement: The sample dataset of the web application
The web application SHALL offer the same fictional sample dataset as the iOS
app. The dataset SHALL hold the same line items, the same budgets, the same
account number, and the same identity marks. Each sample transaction id SHALL
start with `sample-`. Each sample budget SHALL hold the note "Sample budget".

#### Scenario: The user loads the sample data
- **WHEN** the user loads the sample data
- **THEN** the application adds one year of sample transactions up to today,
  three monthly budgets, and two yearly budgets

#### Scenario: The datasets agree
- **WHEN** the web application and the iOS app load the sample data on the
  same day
- **THEN** both hold the same transaction ids, dates, amounts, descriptions,
  and categories

### Requirement: A load adds rows only
The load SHALL add rows, and SHALL NOT change or delete a row of the user. The
load SHALL skip a sample budget when the user has a budget with the same
category and period. A second load SHALL add nothing. The load SHALL NOT run
the rules on the sample transactions.

#### Scenario: The user has a budget for groceries
- **WHEN** the user has a monthly budget for groceries and loads the sample
  data
- **THEN** the application keeps the budget of the user and adds no sample
  budget for groceries

#### Scenario: The user loads the sample data two times
- **WHEN** the sample data is present and the user loads it again
- **THEN** the application adds no row and reports zero added rows

### Requirement: A removal deletes the sample rows only
The removal SHALL delete each sample transaction and each sample budget. It
SHALL NOT delete another row. The application SHALL show the count of the
deleted transactions and budgets.

#### Scenario: The user removes the sample data
- **WHEN** the sample data and real data are present, and the user removes the
  sample data
- **THEN** the application deletes only the sample rows, and the real rows stay

### Requirement: Offer on an empty transactions page
When the database holds no live transaction, the Transactions page SHALL show
an offer to load the sample data. The offer SHALL also tell the user how to
import real data on the Import page.

#### Scenario: The database is empty
- **WHEN** the database holds no live transaction and the user opens the
  Transactions page
- **THEN** the page shows a "Load sample data" button and a link to the Import
  page

#### Scenario: The database holds a transaction
- **WHEN** the database holds at least one live transaction
- **THEN** the Transactions page does not show the offer

### Requirement: Sample data controls on the Import page and the Help page
The Import page and the Help page SHALL each hold a sample data section. The
section SHALL show the load control while the sample data is absent. It SHALL
show the remove control while the sample data is present.

#### Scenario: The sample data is present
- **WHEN** the sample data is present and the user opens the Import page or
  the Help page
- **THEN** the page shows a "Remove sample data" button

#### Scenario: The sample data is absent
- **WHEN** the sample data is absent and the user opens the Import page or the
  Help page
- **THEN** the page shows a "Load sample data" button

### Requirement: Load and remove as POST actions
The application SHALL load and remove the sample data only through a POST
request. A GET request SHALL NOT change the sample data.

#### Scenario: A client sends a GET request
- **WHEN** a client sends a GET request to the load or the remove path
- **THEN** the application changes no row

### Requirement: No export of sample data
The web application SHALL refuse a full export, a delta export, and a share to
the phone while the database holds the sample data. The refusal SHALL tell the
user to remove the sample data first. The fictional rows therefore never reach
another device.

#### Scenario: The user exports with sample data present
- **WHEN** the database holds the sample data and the user starts an export or
  a share
- **THEN** the application writes no file, starts no share server, and tells
  the user to remove the sample data on the Import page or the Help page
