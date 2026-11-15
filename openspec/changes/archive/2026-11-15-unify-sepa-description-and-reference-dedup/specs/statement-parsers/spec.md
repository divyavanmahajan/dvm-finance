# Spec Delta

## MODIFIED Requirements

### Requirement: Structured description from a parser
Each parser SHALL store the fields of its own format as a structured
description, beside the raw text. The rules match on those fields. Two
description forms of one payment type SHALL use the same key for the same
meaning.

#### Scenario: The MT940 description holds tagged fields
- **WHEN** an MT940 description holds tagged fields such as the IBAN, the name,
  and the remittance information of the counterparty
- **THEN** the system makes those fields available as structured values for the
  rules

#### Scenario: A provider export holds columns
- **WHEN** the system parses a PayPal, a Wise, or an SEB export
- **THEN** the structured description keeps the original columns

#### Scenario: The two SEPA forms describe one payment
- **WHEN** the system parses the tagged form and the labelled form of one SEPA
  direct debit
- **THEN** the two structured descriptions hold the same key and the same value
  for the creditor identifier, the mandate reference, the IBAN, the name, the
  remittance information, and the end-to-end reference

## ADDED Requirements

### Requirement: Canonical keys of a SEPA description
The system SHALL use one set of keys for a SEPA payment. They are
`creditor_identifier`, `mandate_reference`, `remittance_info`,
`end_to_end_reference`, `iban`, `bic`, and `name`. The tagged form and the
labelled form SHALL both use these keys.

#### Scenario: The tagged form holds the creditor identifier
- **WHEN** a description holds `/CSID/VP20XNL847867841319`
- **THEN** the structured description holds `creditor_identifier` with the value
  `VP20XNL847867841319`, and it holds no `CSID` entry

#### Scenario: The tagged form holds the mandate reference
- **WHEN** a description holds `/MARF/B0OXIVC5T2O3ZJ58`
- **THEN** the structured description holds `mandate_reference` with the value
  `B0OXIVC5T2O3ZJ58`

#### Scenario: The labelled form holds the remittance information
- **WHEN** a description holds `OMSCHRIJVING: LEBARA NL-03944254 3-277`
- **THEN** the structured description holds `remittance_info`, and it holds no
  `description` entry

#### Scenario: The labelled form holds the reference
- **WHEN** a description holds `KENMERK: KFF5Q4D85TQK39G6`
- **THEN** the structured description holds `end_to_end_reference`, and it holds
  no `reference` entry

### Requirement: Normalized SEPA transaction type
The system SHALL give the same normalized `transaction_type` to the tagged form
and to the labelled form. The system SHALL also report `sepa_type`. For a direct
debit the system SHALL report `direct_debit_type` and `recurring` when the text
names them.

#### Scenario: The tagged form names a recurring direct debit
- **WHEN** a description holds `/TRTP/SEPA INCASSO ALGEMEEN DOORLOPEND`
- **THEN** `transaction_type` is `SEPA Direct Debit`, `sepa_type` is `INCASSO`,
  `direct_debit_type` is `General`, and `recurring` is true

#### Scenario: The tagged form names a transfer
- **WHEN** a description holds `/TRTP/SEPA OVERBOEKING`
- **THEN** `transaction_type` is `SEPA Transfer`, and `sepa_type` is
  `OVERBOEKING`

### Requirement: The format value of a SEPA description
The system SHALL report the format `sepa` for each description that names a SEPA
payment, in the tagged form and in the labelled form. The system SHALL keep the
format `mt940` for a tagged description that names another payment type.

#### Scenario: The tagged form names a SEPA payment
- **WHEN** the `/TRTP/` value starts with `SEPA`
- **THEN** the format is `sepa`

#### Scenario: The tagged form names another type
- **WHEN** the `/TRTP/` value is `IDEAL`
- **THEN** the format stays `mt940`

### Requirement: The Tikkie branch uses the SEPA type
The system SHALL select the Tikkie extraction by `sepa_type`, and not by the
display text of `transaction_type`. The system SHALL extract the same Tikkie
fields from the tagged form as before this change.

#### Scenario: The tagged form holds a Tikkie transfer
- **WHEN** a tagged description holds `/TRTP/SEPA OVERBOEKING` and a remittance
  text that starts with `TIKKIE ID`
- **THEN** the structured description holds `tikkie_id`, `payer_name`, and
  `payer_iban`

### Requirement: The stored structured description uses the canonical keys
The system SHALL rewrite the stored structured description of each SEPA
transaction with the canonical keys, one time. The rules read the stored value,
so a rule on a canonical key SHALL match a row from before this change.

#### Scenario: A stored tagged row holds the old format
- **WHEN** a stored row holds the format `mt940` and a `transaction_type` that
  starts with `SEPA`
- **THEN** the system rewrites its structured description, and the row holds
  `creditor_identifier` and `mandate_reference`

#### Scenario: A stored labelled row holds the old keys
- **WHEN** a stored row holds the format `sepa` with the keys `description` and
  `reference`
- **THEN** the system rewrites its structured description to `remittance_info`
  and `end_to_end_reference`

#### Scenario: A rule matches a row from before the change
- **WHEN** a rule names the field target `end_to_end_reference`, and a row from
  before this change holds that reference
- **THEN** the rule matches that row

#### Scenario: A row holds no SEPA description
- **WHEN** a stored row holds the format `pos`
- **THEN** the system does not change its structured description
