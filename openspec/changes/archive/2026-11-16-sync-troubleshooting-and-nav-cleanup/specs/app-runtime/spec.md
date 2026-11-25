## MODIFIED Requirements

### Requirement: Navigation tabs
The application SHALL show a fixed set of navigation tabs in the top bar. They
are Transactions, Trends, Budgets, Cash Flow, Import, Cash, a QR icon, and Help,
in that order. A "⋮" menu at the right end SHALL hold Export, Rules, Tags, and
Duplicates. The application SHALL mark the current tab or menu item as active,
and it SHALL keep each label on one line. For a tab with no implementation, the
application SHALL render a placeholder, and the page SHALL NOT fail.

#### Scenario: A page renders
- **WHEN** any page renders
- **THEN** the navigation marks the tab of that page as active

#### Scenario: A page from the menu renders
- **WHEN** the user opens the Export, Rules, Tags, or Duplicates page
- **THEN** the "⋮" menu marks that item as active

#### Scenario: The user opens the Cash tab
- **WHEN** the user opens the Cash tab
- **THEN** the application shows the form that adds a hand-entered transaction

#### Scenario: The order of the tabs keeps the two similar names apart
- **WHEN** the navigation renders
- **THEN** the Cash tab stands beside Import, which is the other tab for the
  entry of data, and not beside Cash Flow, which has a similar name and another
  purpose

#### Scenario: The QR icon has an accessible name
- **WHEN** the navigation renders
- **THEN** the QR icon has the accessible name "Share to phone" and a tooltip
  with the same text

## ADDED Requirements

### Requirement: Redirects from the old page paths
The application SHALL redirect a GET request for an old page path to the new
page. `/download` and `/upload` SHALL redirect to `/import`. `/snapshots` SHALL
redirect to `/export`. The redirect SHALL keep the query string.

#### Scenario: The user opens an old bookmark
- **WHEN** the user opens `/download`, `/upload`, or `/snapshots`
- **THEN** the application redirects the browser to the new page

#### Scenario: The old path has a query string
- **WHEN** the user opens `/snapshots?share=1`
- **THEN** the application redirects the browser to `/export?share=1`
