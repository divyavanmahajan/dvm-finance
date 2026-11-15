# Transaction Merge Specification

## Purpose

This capability joins the rows that report one payment into one row. The user
can see the groups before the merge, read a report of each merge, and undo a
merge that the system made.

## Requirements

### Requirement: Discovery of a group of duplicate rows
The system SHALL find each group of live rows of one account that hold the same
end-to-end reference and the same amount. A group holds two rows or more. The
system SHALL ignore an empty reference, the value `NONREF`, and the value
`NOTPROVIDED`. The comparison of the reference SHALL use the normalized form of
the `transaction-dedup` capability. The group SHALL report the original text of
the reference.

#### Scenario: Two rows report one payment
- **WHEN** one account holds two live rows with the end-to-end reference
  `KFF5Q4D85TQK39G6`
- **THEN** the system reports the two rows as one group

#### Scenario: Two accounts hold the same reference
- **WHEN** two accounts each hold one row with the same end-to-end reference
- **THEN** the system reports no group

#### Scenario: The rows hold the value NONREF
- **WHEN** an account holds many live rows with the reference `NONREF`
- **THEN** the system reports no group

#### Scenario: The rows hold the value NOTPROVIDED
- **WHEN** an account holds many live rows with the reference `NOTPROVIDED`
- **THEN** the system reports no group

#### Scenario: The two forms print the reference differently
- **WHEN** one row holds the reference `8022764496926345` and another row of
  the same account and the same amount holds `8022.7644 .9692.6345`
- **THEN** the system reports one group, and the group names the original text

#### Scenario: A payment and its reversal share the reference
- **WHEN** a direct debit of -149,88 and its reversal of +149,88 hold the same
  end-to-end reference
- **THEN** the system reports no group, because the two amounts differ

### Requirement: The survivor of a group is the lowest id
The system SHALL keep the row of the group with the lowest id, in the
lexicographic order. The choice SHALL NOT depend on the import order, the source
file, the source line, or the content of the structured description.

#### Scenario: The group holds two rows
- **WHEN** a group holds the ids `720317081_2024-05-19_-5.75_aaa` and
  `720317081_2024-05-19_-5.75_bbb`
- **THEN** the system keeps the row with the id that ends `aaa`

#### Scenario: Two machines merge the same group
- **WHEN** the user merges one group on two machines before a snapshot sync
- **THEN** the two machines keep the same row, so the payment does not disappear
  from the merged snapshot

### Requirement: The merge carries the manual categorization
The merge SHALL carry the manual category and the manual tags of a flagged row
to the survivor, when the survivor holds none. The merge SHALL NOT overwrite a
value that the survivor already holds.

#### Scenario: The flagged row holds the manual category
- **WHEN** the survivor holds no manual category, and the other row holds the
  manual category `groceries`
- **THEN** the survivor holds the manual category `groceries` after the merge

#### Scenario: The survivor holds the manual category
- **WHEN** the survivor holds the manual category `groceries`, and the other row
  holds none
- **THEN** the manual category of the survivor does not change

### Requirement: The merge refuses a conflict of the manual categories
The system SHALL refuse to merge a group whose rows hold two different manual
categories. The system SHALL report the group to the user. Only the snapshot
import may replace a manual categorization, so the merge SHALL NOT choose
between the two values.

#### Scenario: The two rows hold two different manual categories
- **WHEN** one row of a group holds the manual category `groceries`, and another
  row holds the manual category `restaurant`
- **THEN** the system merges nothing, and the report names the group and the two
  categories

#### Scenario: The two rows hold the same manual category
- **WHEN** each row of a group holds the manual category `groceries`
- **THEN** the system merges the group

### Requirement: The merge flags each other row
The merge SHALL write the time of the merge to `deleted_at` on each row that is
not the survivor. The merge SHALL also write the id of the survivor to
`merged_into` on that row. The merge SHALL NOT delete a row.

#### Scenario: The system merges a group of two rows
- **WHEN** the system merges a group of two rows
- **THEN** the other row stays in the database, holds the time of the merge, and
  names the survivor in `merged_into`

#### Scenario: The lists hide the merged row
- **WHEN** the system merges a group
- **THEN** the transactions list, the trends, the cash flow, and each other
  total hold the survivor one time only

### Requirement: A merged row is not a row that the user flagged
A merged row holds a value in `merged_into`. The purge SHALL NOT delete such a
row, and the list of the flagged transactions SHALL NOT show it. A purge of a
merged row would free its id, and the next import would write the duplicate
again.

#### Scenario: The user purges after a merge
- **WHEN** the system merges a group, and the user then confirms the purge
- **THEN** the purge deletes no merged row, and it reports only the count of the
  rows that the user flagged

#### Scenario: The user opens the list of the flagged transactions
- **WHEN** the system merges a group
- **THEN** the list of the flagged transactions shows no merged row

### Requirement: The preview of the merge
The system SHALL show each group to the user before it merges one. The preview
SHALL name the survivor, each other row, and each group that the system refuses.
The system SHALL merge only after the user confirms.

#### Scenario: The user opens the preview
- **WHEN** the database holds three groups, and one group holds a conflict of
  the manual categories
- **THEN** the preview names the two groups that the system merges, and the one
  group that it refuses

#### Scenario: The user does not confirm
- **WHEN** the user opens the preview and does not confirm
- **THEN** the system changes no row

### Requirement: The report of the merge
The merge SHALL store a report. The report SHALL name each survivor, each
flagged row, each carried manual categorization, and each refused group. The
user SHALL be able to read the report after the merge.

#### Scenario: The system merges two groups
- **WHEN** the system merges two groups
- **THEN** the stored report names the two survivors and the two flagged rows

#### Scenario: The merge carries a manual category
- **WHEN** the merge carries the manual category of a flagged row to the
  survivor
- **THEN** the report names the row, the survivor, and the carried value

### Requirement: The undo of a merge
The system SHALL let the user undo a merge. The undo SHALL clear `deleted_at`
and `merged_into` on each row of the merge. The undo SHALL NOT remove a manual
categorization that the merge carried to the survivor.

#### Scenario: The user undoes a merge
- **WHEN** the user undoes a merge of a group of two rows
- **THEN** the two rows appear again in the transactions list and in each total

#### Scenario: The purge already deleted a row
- **WHEN** the user undoes a merge, and the database holds the survivor only
- **THEN** the system reports that it cannot restore the other row

### Requirement: Discovery of a group with no reference
The system SHALL find a group of live rows that hold no usable end-to-end
reference, by the account, the transaction date, the amount, the counterparty
IBAN, and the remittance text. A transfer between two accounts of the user
carries no reference, so only this key finds its group.

#### Scenario: Two forms of a transfer with no reference
- **WHEN** one account holds two live rows of one transfer of -1000,00 euro,
  each from another statement file, and both hold the reference `NOTPROVIDED`
- **THEN** the system reports the two rows as one group

#### Scenario: The rows hold a usable reference
- **WHEN** two rows hold the same usable end-to-end reference
- **THEN** the system reports one group by the reference, and it does not report
  a second group for the same rows

### Requirement: Refusal of a group from one statement file
The system SHALL refuse a group of the second key when one statement file gives
more than one row of it. Such a group holds a genuine repeated payment. The
system SHALL report the refused group with that reason.

#### Scenario: One file gives two rows of the group
- **WHEN** a group of the second key holds two rows of one statement file
- **THEN** the system merges nothing, and the report names the group with the
  reason of the statement file

#### Scenario: Each file gives one row
- **WHEN** a group of the second key holds one row of each of two statement
  files
- **THEN** the system merges the group

### Requirement: The report names the key of a group
Each merged group and each refused group SHALL name the key that found it. The
value is the reference or the counterparty. The user can therefore see why the
system joined two rows.

#### Scenario: The reference found the group
- **WHEN** the system merges a group that the end-to-end reference found
- **THEN** the report names the reference as the key of that group

#### Scenario: The counterparty found the group
- **WHEN** the system merges a group that the second key found
- **THEN** the report names the counterparty IBAN and the remittance text as the
  key of that group
