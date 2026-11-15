# Tasks

## 1. Field rows in Python

- [x] 1.1 Write failing tests in `tests/test_rule_prefill.py` for `build_field_rows`: the field order, the skip of empty fields, the `contains` default, and the `payer_iban` case. Verify that the tests fail.
- [x] 1.2 Add `build_field_rows(txn, vm)` to `core/rule_prefill.py`. Verify that the tests of 1.1 pass.
- [x] 1.3 Add tests for a draft on a sample: the primary row, the leading `AND` conditions, the stop at the first `OR`, a second condition on the same field, and a draft field that the sample does not hold. Make them pass, and verify that the remaining conditions go back for the advanced builder.
- [x] 1.4 Make `prefill_rule_from_transaction` return the rows with the heuristic row and the account filter selected. Verify that each existing prefill test still passes.

## 2. Routes

- [x] 2.1 Pass the field rows and the advanced conditions from `/rules/new?from_transaction=` to the template. Verify with a client test in `tests/test_rules_ui.py` that the page shows a selected `merchant_name` row.
- [x] 2.2 Add `POST /rules/sample`. It reads the form and `sample_transaction_id`, and returns `_rule_match_card.html` with `HX-Trigger: rule-sample-loaded`. Verify with client tests for an edit draft, an unknown id (status 404), and no database write.
- [x] 2.3 Verify with a client test that `/rules/{id}/edit` shows no field list and still shows the saved primary match, conditions, and filters.

## 3. Editor template and Alpine component

- [x] 3.1 Move the Match card into the partial `_rule_match_card.html`. Add the field rows, the filter rows with checkboxes, and the "Advanced conditions" section with its help text. Remove the filter card from the right column. Verify that `/rules/new` and `/rules/{id}/edit` render with status 200.
- [x] 3.2 Add the Alpine component `ruleMatch` to `static/js/rules.js`. It writes the hidden primary inputs and the `AND` `cond_*` inputs from the selected rows, and it disables each unselected filter input. Verify with a client test that a posted form of this shape saves the expected rule.
- [x] 3.3 Show a message in the editor when the field list shows and the user selects no row. The preview and the save answer "Select at least one field." Verify with client tests and in the browser.
- [x] 3.4 Run the preview when the editor opens from a transaction: the Match card fires `rule-auto-preview` after Alpine fills the hidden inputs. The preview button also listens for `rule-sample-loaded`. Verify in the browser that the preview runs on open from a transaction.

## 4. Preview sample button

- [x] 4.1 Add a "Use as sample" button to each row of `txn_table` in `_rule_preview.html`. The button posts the form to `/rules/sample` and swaps the Match card. Verify with a client test that the preview HTML holds the button with the transaction id.

## 5. Docs and flows

- [x] 5.1 Update the rule editor section of `docs/product.md` in ASD-STE100. Describe the field list, the filter rows, the advanced conditions, and "Use as sample". Verify that the text matches the UI.
- [x] 5.2 Update `test_flow_b_create_rule_from_uncategorized` in `tests/e2e/test_flows_e2e.py` for the new rows. Add a step to `test_flow_d_edit_rule_preview_diff_save_history` that selects a sample and saves. Verify that `pytest -m e2e` passes.

## 6. Integration checks

- [x] 6.1 Run `pytest`, `pytest --cov=abn_combined`, and `ruff check .`. Verify that all pass and that the coverage stays at 80% or more.
- [x] 6.2 Start the app with `--data-dir ./devdata`. Create a rule from a transaction, and edit a rule with a sample, in a real browser. Verify that the saved rules match the preview.
- [x] 6.3 Run `openspec validate rule-editor-field-checklist --strict`. Verify that it passes.

## Workflow follow-up

- Archive the change after the user reviews and accepts it.
