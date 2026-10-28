# Rule Matching Specification

## Purpose

This capability defines when a rule matches a transaction. It also defines how
the system applies the matching rules to assign a category and tags. The same
input therefore always gives the same categorization.

## Requirements

### Requirement: Normalization before a comparison
Before a comparison, the system SHALL normalize the field value and the match
value. The system SHALL remove each whitespace character, then remove the
literal text `WERO/`, and then change the text to lower case. An absent value
SHALL normalize to an empty string.

#### Scenario: The field holds whitespace and the prefix
- **WHEN** the field value is `WERO /Albert Heijn`, and the match value is
  `albertheijn`
- **THEN** the two values are equal after the normalization

#### Scenario: The case differs
- **WHEN** the field value is `ALBERT HEIJN`, and the match value is
  `albert heijn`
- **THEN** the rule matches

### Requirement: Match patterns
The system SHALL support `contains`, `exact`, `starts_with`, and `ends_with`
against the normalized values. The system SHALL support `regex` as a search of
the raw pattern against the normalized field value, and the search ignores the
case. An unknown pattern SHALL NOT match. A regular expression that does not
compile at match time SHALL NOT match.

#### Scenario: The pattern is ends-with
- **WHEN** the pattern is `ends_with` with the value `heijn`, and the field is
  `albert heijn`
- **THEN** the rule matches

#### Scenario: The pattern is a regular expression
- **WHEN** the pattern is `regex` with the value `ah\d+`, and the field is
  `AH 1234`
- **THEN** the rule matches, because the system normalizes the field to `ah1234`
  before the search

### Requirement: Primary condition for each rule type
The system SHALL evaluate the primary condition of a rule by its rule type. The
system SHALL compare a boolean structured value as the text `true` or `false`.

#### Scenario: The transaction has no structured description
- **WHEN** the system evaluates a structured-field rule against a transaction
  with no structured description
- **THEN** the rule does not match

#### Scenario: The system recovers an IBAN from the description
- **WHEN** the transaction of an IBAN rule has no structured IBAN, but its
  description holds `IBAN: NL02ABNA0123456789`
- **THEN** the system uses that IBAN for the comparison

#### Scenario: An IBAN rule uses a pattern
- **WHEN** an IBAN rule uses `ends_with` with the value `0123456789`
- **THEN** the rule matches a transaction whose IBAN ends with those digits
- **AND** an IBAN rule also supports `exact` and `contains`

#### Scenario: The rule names a structured field
- **WHEN** a structured-field rule names a field in the parsed structured
  description of the transaction
- **THEN** the system compares the value of that field against the match value

#### Scenario: The rule targets the description
- **WHEN** the type of a rule is full-description, or its field target is the
  description
- **THEN** the system compares the raw description against the match value

#### Scenario: The rule names an unknown field
- **WHEN** a rule names a field target that is neither the description nor a
  field in the structured data
- **THEN** the rule does not match

### Requirement: Combination of the extra conditions
The system SHALL fold the extra conditions of a rule in their stored order. The
fold starts from a true accumulator. An `AND` condition conjoins its result, and
an `OR` condition disjoins it. The rule SHALL match only when the primary
condition and the result of the fold are both true.

#### Scenario: An AND condition comes before an OR condition
- **WHEN** the conditions are, in order, an `AND` condition that fails and an
  `OR` condition that succeeds
- **THEN** the result of the fold is true, and the rule can match

#### Scenario: One AND condition fails
- **WHEN** the one extra condition is an `AND` condition that fails
- **THEN** the rule does not match, although its primary condition matches

### Requirement: Context filters
The account filter, the currency filter, and the date-range filter of a rule
SHALL each restrict the match further, when the rule sets them. An unset filter
SHALL impose no restriction. The system SHALL treat a date bound as inclusive.

#### Scenario: The rule filters on an account
- **WHEN** a rule filters on one account
- **THEN** the rule does not match a transaction of another account

#### Scenario: The date bound equals the transaction date
- **WHEN** the date range of a rule starts on the date of the transaction
- **THEN** the transaction stays eligible

### Requirement: Two passes
A reapplication SHALL run two passes across the selected transactions. The first
pass holds the category rules. The second pass holds the tag-only rules.

#### Scenario: Two types of rule match one transaction
- **WHEN** a category rule and a tag-only rule both match one transaction
- **THEN** the system assigns the category first and merges the tags of the
  tag-only rule afterwards

### Requirement: First match by priority in the category pass
In the first pass, the system SHALL take the active category rules in ascending
priority order, and break a tie on the rule id. The first match SHALL win. The
pass SHALL skip a transaction whose categorization source is manual. The system
SHALL write the lower-case category of the winning rule, its tags, and its id as
the categorization source.

#### Scenario: Two rules match one transaction
- **WHEN** two active rules match one transaction with the priorities 10 and 50
- **THEN** the rule with the priority 10 assigns the category

#### Scenario: The transaction is manual
- **WHEN** the categorization source of a transaction is manual
- **THEN** the first pass changes neither its category, nor its tags, nor its
  source

#### Scenario: No rule matches
- **WHEN** no active category rule matches a non-manual transaction
- **THEN** the system clears its category and its tags, and the transaction
  reads as uncategorized

#### Scenario: The match reproduces the current values
- **WHEN** a match gives a transaction the category and the tags that it already
  holds
- **THEN** the system reports no change, and it still sets the categorization
  source to the id of that rule

### Requirement: Report and stamp for each change
A reapplication SHALL return the category and the tags before and after the
change, for each transaction that it changed. The system SHALL stamp each
changed transaction as updated, so that a delta snapshot can find it.

#### Scenario: A run changes three transactions
- **WHEN** a reapplication changes 3 transactions out of 1,000
- **THEN** the system reports exactly those 3 transactions, each one with its old
  and new category and tags
- **AND** each one holds a new update stamp

### Requirement: Reapplication across a subset
A reapplication SHALL run across a named subset of the transactions. The system
categorizes a newly imported batch in this manner, and it leaves the other
transactions alone.

#### Scenario: A run covers one import
- **WHEN** a reapplication runs for the ids of a batch that the system just
  imported
- **THEN** the system modifies no transaction outside that batch
