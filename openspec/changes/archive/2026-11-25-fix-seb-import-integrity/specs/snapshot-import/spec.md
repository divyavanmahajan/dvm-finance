## ADDED Requirements

### Requirement: An old SEB id in a snapshot
Before the merge, the snapshot import SHALL change each incoming SEB id in the
old form (the account and the voucher number only) to the SEB voucher key. It
SHALL take the fields from the structured description of the incoming row. It
SHALL change each reference to the old id in the snapshot in the same manner.

#### Scenario: A snapshot from an older app version
- **WHEN** a snapshot holds the SEB row `seb:divyavanmahajan_5400000001`, and
  the local database holds the same transaction with its new id
- **THEN** the import matches the two rows and adds no second row

#### Scenario: A snapshot with the new ids
- **WHEN** a snapshot holds SEB rows with the SEB voucher key
- **THEN** the import uses each id as it is
