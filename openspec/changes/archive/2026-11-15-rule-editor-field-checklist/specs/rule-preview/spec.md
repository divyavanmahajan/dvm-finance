# Spec Delta

## ADDED Requirements

### Requirement: Selection of a sample from a preview
Each transaction row of a preview SHALL show a "Use as sample" button. The
button SHALL make that transaction the sample transaction of the editor. The
button SHALL write nothing to the database. After the sample loads, the editor
SHALL run the preview again.

#### Scenario: The user selects a sample on "Edit rule"
- **WHEN** the user previews a saved rule and selects "Use as sample" on a
  matched transaction
- **THEN** the Match card shows the field list of that transaction, and the
  preview runs again

#### Scenario: The user selects a sample from the lost transactions
- **WHEN** the user selects "Use as sample" on a transaction in the lost set
- **THEN** the field list shows the fields of that transaction, and the system
  stores no rule change
