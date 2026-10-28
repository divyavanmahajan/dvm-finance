# Transaction Filtering Specification

## Purpose

The query string holds the complete transaction filter. Each filtered view is
therefore a bookmark and a shareable link. It is also the target of a link from
the trends, the budgets, the cash flow, or a rule.

## Requirements

### Requirement: Filter state in the URL
The query string SHALL hold each part of the transaction filter state. The state
SHALL make a round trip: the system parses a query string, and it serializes an
equivalent filter again.

#### Scenario: A full filter makes a round trip
- **WHEN** a query string sets a search term, a date range, two categories, a
  tag, an account, an amount range, a sort, and a page
- **THEN** the system reproduces each of those values when it serializes the
  parsed filter

#### Scenario: The filter holds only defaults
- **WHEN** the filter uses the default sort and page 1
- **THEN** the serialized query string holds no `sort` parameter and no `page`
  parameter

### Requirement: Supported filter parameters
The system SHALL accept `q`, `date_from`, `date_to`, and `preset`. It SHALL
accept a repeated `category`, a repeated `exclude_category`, a repeated `tag`,
and a repeated `account`. It SHALL accept `amount_min`, `amount_max`, `rule_id`,
`source_file`, `include_transfers`, `sort`, and `page`. The system SHALL ignore
a value that it cannot parse or does not know. The request SHALL NOT fail.

#### Scenario: The request holds values that the system cannot parse
- **WHEN** the query string holds `date_from=not-a-date`, `amount_min=abc`,
  `sort=bogus`, and `preset=whenever`
- **THEN** the request succeeds with no date filter, no amount filter, the
  default sort, and no preset

#### Scenario: The page number is zero or negative
- **WHEN** the request asks for `page=0` or `page=-3`
- **THEN** the system uses page 1

### Requirement: Text search
A search term SHALL match the raw description or the structured description. The
comparison ignores the case.

#### Scenario: The term is only in the structured description
- **WHEN** the term appears only in the structured description of a transaction
- **THEN** the system includes that transaction

### Requirement: Date range and presets
The system SHALL support an explicit inclusive date range. The system SHALL also
support the presets `this-month`, `last-month`, `this-year`, and `last-year`. A
preset takes priority over the explicit dates.

#### Scenario: The request holds a preset and explicit dates
- **WHEN** the request holds `preset=this-month` and explicit `date_from` and
  `date_to` values
- **THEN** the system uses the inclusive range of the month and ignores the
  explicit dates

#### Scenario: The last month is in the previous year
- **WHEN** today is in January, and the request holds `preset=last-month`
- **THEN** the range covers the complete previous December

### Requirement: Category include and exclude filters
A category filter SHALL match on the effective category, where the manual value
takes precedence. It SHALL use subtree matching. The system SHALL support an
include list and an exclude list. The user SHALL also be able to select the
pseudo-category `uncategorized`.

#### Scenario: The include list holds two categories
- **WHEN** the request holds `category=groceries` and `category=fuel`
- **THEN** the system includes a transaction in either category or either
  subtree

#### Scenario: The request excludes a category
- **WHEN** the request holds `exclude_category=groceries`
- **THEN** a transaction with no category stays in the result

#### Scenario: The request excludes the uncategorized state
- **WHEN** the request holds `exclude_category=uncategorized`
- **THEN** only a transaction with an effective category stays in the result

### Requirement: Tag filter
A tag filter SHALL match the effective tags, where the manual tags take
precedence over the rule-assigned tags. The comparison ignores the case. Several
tags form a union.

#### Scenario: The request holds two tags
- **WHEN** the request holds `tag=recurring` and `tag=holiday`
- **THEN** the system includes a transaction that holds either tag

#### Scenario: The tag is part of a longer tag
- **WHEN** the request holds `tag=food`, and a transaction holds the tag
  `fast-food`
- **THEN** the system includes that transaction, because the filter matches a
  substring of the joined tag list
- **AND** this behavior differs from a tag rename and a tag delete, which match
  a complete comma-separated entry

### Requirement: Amount range filter
The system SHALL apply an amount bound to the absolute value of the amount. A
range therefore selects an income and an expense of that size. Each bound is
optional.

#### Scenario: The request holds a lower bound
- **WHEN** the request holds `amount_min=100`
- **THEN** the system includes a transaction of +150 and a transaction of -150

### Requirement: Provenance filters
The system SHALL filter by the rule that assigned the category of a transaction,
through `rule_id`. The system SHALL also filter by the file that a transaction
came from, through `source_file`.

#### Scenario: The request holds a rule id
- **WHEN** the request holds `rule_id=7`
- **THEN** the system includes only a transaction whose categorization source is
  rule 7

### Requirement: Removable chips for the active filters
The system SHALL show each active filter as a chip. Each chip SHALL hold a label
and a link that removes only that filter and resets the page to 1.

#### Scenario: The user removes one of two categories
- **WHEN** two categories are active, and the user removes one chip
- **THEN** the new query string keeps the other category and drops `page`

#### Scenario: The user removes the date chip
- **WHEN** the user removes the date chip
- **THEN** the system clears `date_from`, `date_to`, and `preset`
