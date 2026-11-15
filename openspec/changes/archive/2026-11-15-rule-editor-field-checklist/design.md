# Design

## Context

The rule editor is `rules_edit.html` with the Alpine component `ruleEditor` in
`static/js/rules.js`. The editor posts flat form fields: `rule_type`,
`field_target`, `match_pattern`, `match_value`, the `cond_*` lists, and the
`filter_*` fields. `_parse_rule_form` in `api/rules.py` reads these fields for
the preview, the create, and the update. The save path goes through
`record_rule_change`.

`prefill_rule_from_transaction` in `core/rule_prefill.py` returns a view-model
for one rule. It does not return the other fields of the transaction.

The matcher reads a condition field from `description` or from the
`description_structured` JSON. The primary match has special logic for an
`account_iban` rule: it also finds an IBAN in the description text.

The route `/rules/new?from_transaction=` passes `auto_preview=True`, but the
template does not use the flag. The preview therefore does not run at once.

## Goals / Non-Goals

**Goals:**
- Keep the posted form and the server-side save unchanged.
- Keep the row logic in Python, so that unit tests cover it.

**Non-Goals:**
- No change to the matcher, the rule model, or the snapshot format.
- No sample picker outside the preview, for example a search box.
- No field rows for the amount or the date. The matcher cannot match on these
  fields today.

## Decisions

### 1. The browser converts the rows into the existing form fields

The Alpine component holds the rows. Before a preview or a save, it writes
hidden inputs: the first selected row gives `field_target`, `match_pattern`,
and `match_value`. The other selected rows give `cond_*`
entries with the operator `AND`, before the advanced conditions. An unselected
filter row disables its input, so the browser does not send it. The server
then reads an empty filter.

Alternative: post the rows as new form fields and convert them on the server.
This changes `_parse_rule_form`, the validation, and its tests for no gain to
the user. We reject it.

### 2. Python builds the rows

A new pure function `build_field_rows(txn, vm)` in `core/rule_prefill.py`
returns the ordered rows. Each row holds `field`, `value`, `pattern`, and
`selected`. The function applies these steps:

1. Collect the fields of the transaction in the order of the spec. Skip each
   empty structured field.
2. Map the primary match of `vm` to its field. A `keyword` rule and a
   `full_description` rule map to `description`. Select that row with the
   pattern and the value of `vm`.
3. Walk the conditions of `vm` up to the first `OR`. Select the row of each
   field with its pattern and value. Skip a field that an earlier step
   selected. The function returns the remaining conditions for the advanced
   builder.
4. Add a selected row for each draft field that the sample does not hold.

`prefill_rule_from_transaction` calls this function. The default selection
therefore comes from the existing heuristic. The heuristic today puts a
`payer_iban` value into an `iban` rule when the transaction has no `iban`. The
function keeps this: it adds an `iban` row with the `payer_iban` value in that
case, so the existing prefill tests stay valid.

The rows carry no rule type. The save path in `api/rules.py` ignores the posted
`rule_type` and derives the type from `field_target` (`_derive_rule_type`).
The matcher reads `description` or the structured field for a `keyword` rule,
so a row on any field matches as the user expects.

### 3. A route returns the Match card for a sample

`POST /rules/sample` reads the current form and `sample_transaction_id`. It
returns the partial `_rule_match_card.html`. The "Use as sample" button posts
the form with `hx-include="#rule-form"` and swaps the Match card. The Assign
card is outside the swap target, so the editor keeps it. The response sets
`HX-Trigger: rule-sample-loaded`, and the preview button listens for this event
and runs again.

Alternative: a full page load with `?sample=<id>` in the URL. This loses each
unsaved edit. The sample is draft state and not a filter, so the URL rule does
not apply to it. We reject the full load.

### 4. The Match card has its own Alpine component

The Match card gets its own `x-data="ruleMatch(...)"`. The swap replaces the
element, and Alpine starts the new component. The Assign card keeps the
`isTagOnly` state in the form component.

### 5. The editor runs the preview on load from a transaction

When `auto_preview` is true, the preview button gets `hx-trigger="click, load"`.
This closes the gap between the spec and the template.

## Risks / Trade-offs

- [A selected row changes the order of a saved rule. A rule on `description`
  with an `AND` condition on `name` gets `name` as the primary match after a
  sample loads.] → The result does not change, because `AND` has no order.
  The preview shows the effect before the save.
- [The save stores each rule as a `keyword` rule, so no saved rule finds an
  IBAN in the description text.] → This is the current save behavior, and this
  change does not alter it. The field list shows the `iban` row only when the
  sample holds a structured `iban`.
- [The preview skips manual transactions, so the user cannot select a manual
  transaction as a sample.] → The user can open "Create rule" from that
  transaction on the transactions page.
- [The browser builds the hidden inputs. A script error sends an empty match.]
  → The server validation rejects an empty match value. A Playwright flow
  covers the save.
- [Advanced `OR` conditions follow the selected rows. The main match must
  always match. The matcher then evaluates the conditions from left to right,
  so the result is `main AND ((other rows) OR condition)`.] → This is the
  current behavior of the builder. The help text of the advanced section
  states it.

## Migration Plan

No data migration. The change is a template, route, and JavaScript change. To
roll back, revert the commit.
