# Transaction Browsing Specification

## Purpose

This capability lets the user read the imported transactions as a filtered,
sorted, paginated table with a detail view for each row. Each other view can
therefore link into the exact list of transactions behind a number.

## Requirements

### Requirement: Transactions table page
The system SHALL serve the transactions table as the main screen of the
application. The system SHALL render the same table for an alias path, so that a
link from another view resolves to the same view.

#### Scenario: The user opens the main screen
- **WHEN** the user opens `/`
- **THEN** the page renders the filter bar and the table, and it marks the
  Transactions tab as active

#### Scenario: The user opens a deep link
- **WHEN** the user opens `/transactions` with a filter query string
- **THEN** the same page renders with those filters, and it still marks the
  Transactions tab as active

### Requirement: Partial refresh of the table
The system SHALL serve the table as a separate partial for an incremental
update. The system SHALL return the complete page if the user opens the partial
URL directly.

#### Scenario: A request carries the partial-request header
- **WHEN** a request to `/transactions/table` carries the header
  `HX-Request: true`
- **THEN** the system returns only the table fragment

#### Scenario: The user opens the partial URL directly
- **WHEN** the user opens or refreshes `/transactions/table` without that header
- **THEN** the system returns the complete page, and not a bare fragment

### Requirement: Server-side pagination
The system SHALL paginate the filtered result on the server at 50 rows for each
page. The system SHALL clamp a page number that is out of range to the last
page.

#### Scenario: The page number is past the end
- **WHEN** the filter selects 120 transactions, and the request asks for page 9
- **THEN** the system returns page 3, which is the last page

#### Scenario: The filter selects nothing
- **WHEN** the filter selects no transaction
- **THEN** the system reports one empty page and a total of 0

### Requirement: Column sorting
The system SHALL sort by the date, the description, the amount, the effective
category, or the effective tags. A click on an inactive column SHALL sort it in
ascending order. A click on the active column SHALL reverse it. A sort SHALL
reset the page to 1 and break a tie on the transaction id.

#### Scenario: The user clicks an inactive column
- **WHEN** the active sort is `date_desc`, and the user clicks the Amount header
- **THEN** the sort becomes `amount_asc`, and the page resets to 1

#### Scenario: The user clicks the active column
- **WHEN** the active sort is `amount_asc`, and the user clicks the Amount
  header
- **THEN** the sort becomes `amount_desc`

### Requirement: Summary of the filtered result
The system SHALL report the total amount, the earliest transaction date, and
the latest transaction date. These values cover the complete filtered result,
and not only the visible page.

#### Scenario: The filter spans several pages
- **WHEN** a filter selects 200 transactions across 4 pages
- **THEN** the total amount and the date range on the page cover all 200 rows

### Requirement: Detail view for a row
The system SHALL provide a detail view for each transaction. The view SHALL show
each stored field, the key and value pairs of the parsed structured description,
and the rule that assigned the current category.

#### Scenario: The user opens the detail of a rule-categorized transaction
- **WHEN** the user opens the detail view of a transaction whose categorization
  source is a rule
- **THEN** the view shows the structured description fields and names that rule

#### Scenario: The request names an unknown transaction
- **WHEN** a detail request names a transaction id that does not exist
- **THEN** the system responds with status 404

### Requirement: Facet options for the filter bar
The system SHALL offer the filter bar the distinct accounts, categories, and
tags in the data. The category options SHALL hold the values from the rules and
from the transactions. They SHALL also hold each ancestor prefix of a
hierarchical category, so that the user can select a complete subtree.

#### Scenario: The data holds one deep category
- **WHEN** the only stored category is `fixed-insurance-life`
- **THEN** the category options hold `fixed`, `fixed-insurance`, and
  `fixed-insurance-life`

#### Scenario: Only a rule holds a category
- **WHEN** no transaction has a category, but a rule assigns `groceries`
- **THEN** the system still offers `groceries` as a filter option
