# iOS Transaction Review Specification

## Purpose

This capability lets the user read and search the transactions on an iPhone and
an iPad, with no network connection. It is the review half of the companion app.

## Requirements

### Requirement: A standalone offline companion
The app SHALL hold its own local database. The app SHALL never open the database
file of the desktop application. Each exchange of data SHALL use the
gzipped-JSON snapshot format.

#### Scenario: The user works with no network and no computer
- **WHEN** the user works with no network and no computer present
- **THEN** the browse, filter, and edit functions work against the local
  database

### Requirement: Tabbed navigation
The app SHALL show Transactions, Trends, Budgets, Import, and Help as its
top-level tabs.

#### Scenario: The app starts
- **WHEN** the app starts
- **THEN** those five tabs are available

### Requirement: Transaction list
The transactions tab SHALL list the transactions in groups by date. Each row
SHALL show the effective category and the effective tags. The app SHALL let the
user search by text.

#### Scenario: The app shows the list
- **WHEN** the app shows the list
- **THEN** the transactions appear in groups under their dates

#### Scenario: The user types a search term
- **WHEN** the user types a search term
- **THEN** the list narrows to the transactions that match it

### Requirement: Parity of the filters with the desktop application
The filter sheet SHALL offer an include picker and an exclude picker for the
categories. It SHALL also offer an account filter, a date range, an
uncategorized-only option, and a transfers toggle. The app SHALL build the
category pickers from the distinct effective categories. A category filter SHALL use the same hyphen-subtree
matching as the desktop application. The app SHALL exclude the transfers by
default.

#### Scenario: The user selects a parent category
- **WHEN** the user selects a parent category
- **THEN** the app includes its descendants, as the desktop application does

#### Scenario: The user has not touched the filter sheet
- **WHEN** the user has not touched the filter sheet
- **THEN** the list holds no transaction whose effective category starts with
  the transfer prefix

### Requirement: Filter state through the navigation
The app SHALL carry the filter state as one value through the navigation. A
tap-through from the trends and the transactions screen therefore share one
mechanism. This is the equivalent of the URL rule of the desktop application.

#### Scenario: The user arrives from the trends
- **WHEN** the user taps a trends cell
- **THEN** the transactions screen opens with the equivalent filter

### Requirement: Transaction detail
A tap on a transaction SHALL show each stored field. It SHALL also show the key
and value pairs of the structured description. It SHALL also show the rule that
categorized the transaction, and the source file and line.

#### Scenario: The user opens a transaction
- **WHEN** the user opens a transaction
- **THEN** the detail shows the structured description fields and the rule that
  categorized it

### Requirement: Parity of the identity with the desktop application
For the same input, the app SHALL produce the same transaction ids, rule UUIDs,
normalization, and content hash as the desktop application. A snapshot therefore
merges across the devices without a heuristic.

#### Scenario: The user imports the same file on both
- **WHEN** the user imports the same statement file on the desktop application
  and on the phone
- **THEN** both produce the same transaction ids
- **AND** a snapshot exchange reports them as the same transactions

### Requirement: Layout and appearance
The app SHALL support the iPhone and the iPad. It SHALL use a split layout on
the iPad where that helps. It SHALL follow the light and dark appearance of the
system.

#### Scenario: The app runs on an iPad
- **WHEN** the app runs on an iPad
- **THEN** the app can show the transaction list and the detail side by side
