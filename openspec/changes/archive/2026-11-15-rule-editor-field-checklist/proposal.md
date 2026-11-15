# Proposal

## Why

When the user creates a rule from a transaction, the editor shows only one field
that the system selects. The user cannot see the other fields of the
transaction. To match on more fields, the user must type each field name and
value into an extra condition by hand.

The context filters are in a closed panel in the right column. The user
therefore does not see that the system limits the rule to the source account.

## What Changes

- The Match card shows a field list for a sample transaction. The list has one
  row for the description and one row for each structured field that holds a
  value.
- Each row holds a checkbox, the field name, a pattern selector, and a value
  that the user can edit. The value starts as the value from the transaction.
- The first selected row becomes the primary match of the rule. Each other
  selected row becomes an `AND` condition.
- The context filters (account, currency, date from, date to) move into the
  Match card. Each filter becomes a row with a checkbox. The account and the
  currency start with the values from the transaction.
- When the editor opens from a transaction, the editor selects the field that
  the current prefill heuristic picks, and the account filter. The editor
  clears all other rows.
- The manual condition builder stays below the field list, with the name
  "Advanced conditions". The user uses it for `OR` logic and for a field that
  the sample does not hold.
- Each row of the preview gets a "Use as sample" button. The button loads the
  field list from that transaction and keeps the current draft. This also
  gives the field list to "Edit rule" and to a blank new rule.
- The right column holds only the Assign card.
- The editor runs the preview when it opens from a transaction. The current
  spec requires this, but the template does not do it.

The saved rule format does not change. The editor still posts the same form
fields, so the save, the validation, and `record_rule_change` stay the same.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `categorization-rules`: The requirement "Creation of a rule from a
  transaction" changes, because the editor now shows a field list and
  selects defaults in it. New requirements cover the field list, the context
  filter rows, the advanced conditions, and the sample transaction for an
  edit.
- `rule-preview`: A new requirement adds the "Use as sample" action to each
  preview row.

## Impact

- `src/abn_combined/core/rule_prefill.py`: a new pure function builds the field
  rows from a transaction and a rule draft.
- `src/abn_combined/api/rules.py`: a new route returns the Match card for a
  draft and a sample transaction. The `new` and `edit` routes pass the field
  rows to the template.
- `src/abn_combined/web/templates/rules_edit.html`: a new layout for the Match
  card. The context filters move. A new partial holds the Match card.
- `src/abn_combined/web/templates/_rule_preview.html`: a "Use as sample"
  button on each transaction row.
- `src/abn_combined/web/static/js/rules.js`: the Alpine component converts the
  selected rows into the existing form fields.
- Tests: `tests/test_rule_prefill.py`, `tests/test_rules_ui.py`, and one
  Playwright flow.
- Docs: `docs/product.md` (rule editor section).
- No schema change, no snapshot change, and no iOS change. The iOS app has no
  rule editor.
