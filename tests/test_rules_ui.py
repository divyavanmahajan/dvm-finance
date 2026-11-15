"""TestClient tests for the Rules UI: CRUD, conditions, preview, prefill, history."""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

from abn_combined.core.models import (
    CategorizationRule,
    RuleChangeReport,
    RuleCondition,
    Transaction,
)
from abn_combined.db import get_session_factory


def _mk_txn(**kw) -> Transaction:
    base = dict(
        accountNumber="NL01",
        transactiondate=date(2024, 1, 15),
        amount=-10.0,
        currency="EUR",
        description="Test transaction",
    )
    base.update(kw)
    base.setdefault("id", f"{base['accountNumber']}-{base['description']}")
    return Transaction(**base)


@pytest.fixture
def seed(app):
    """Seed transactions + two rules; return the session factory."""
    factory = get_session_factory()
    db = factory()
    db.add_all([
        _mk_txn(id="t1", description="ALBERT HEIJN 1234 groceries",
                description_structured=json.dumps({"merchant_name": "ALBERT HEIJN"})),
        _mk_txn(id="t2", description="Rent payment to landlord"),
        _mk_txn(id="t3", description="SEPA overboeking IBAN: NL91ABNA0417164300 J DOE",
                description_structured=json.dumps({"iban": "NL91ABNA0417164300"})),
        _mk_txn(id="t4", description="Coffee corner purchase",
                manual_category="food:coffee", categorization_source="manual"),
    ])
    r1 = CategorizationRule(
        priority=10, rule_type="keyword", match_pattern="contains",
        field_target="description", match_value="albert heijn",
        category="food:groceries", tags="ah", is_active=True,
    )
    r2 = CategorizationRule(
        priority=50, rule_type="keyword", match_pattern="contains",
        field_target="description", match_value="rent",
        category="housing", is_active=True,
    )
    r2.conditions.append(RuleCondition(
        field_target="description", match_pattern="contains",
        match_value="landlord", operator="AND", sort_order=0,
    ))
    db.add_all([r1, r2])
    db.commit()
    ids = (r1.id, r2.id)
    db.close()
    return factory, ids


def _reports(factory, action=None):
    db = factory()
    q = db.query(RuleChangeReport)
    if action:
        q = q.filter(RuleChangeReport.action == action)
    reports = q.order_by(RuleChangeReport.id).all()
    db.close()
    return reports


# ---------------------------------------------------------------------------
# List page
# ---------------------------------------------------------------------------


def test_list_renders_rules_by_priority(client, seed):
    r = client.get("/rules")
    assert r.status_code == 200
    body = r.text
    # <code>-wrapped match values avoid chrome substrings (e.g. "cur*rent*").
    assert body.index(">albert heijn<") < body.index(">rent<")
    assert "food:groceries" in body and "housing" in body


def test_list_matched_count_links_to_transactions(client, seed):
    factory, (r1_id, _) = seed
    # attribute t1 to rule 1
    db = factory()
    t1 = db.get(Transaction, "t1")
    t1.category, t1.categorization_source = "food:groceries", str(r1_id)
    db.commit()
    db.close()
    r = client.get("/rules")
    assert f"/transactions?rule_id={r1_id}" in r.text


def test_list_empty_state(client, app):
    r = client.get("/rules")
    assert r.status_code == 200
    assert "No rules" in r.text


# ---------------------------------------------------------------------------
# Sortable column headers
# ---------------------------------------------------------------------------


def test_list_headers_are_sortable_links(client, seed):
    r = client.get("/rules")
    body = r.text
    assert "sortable-th" in body
    assert "sort=priority_desc" in body  # default sort is priority_asc


def test_sort_by_priority_desc(client, seed):
    r = client.get("/rules?sort=priority_desc")
    body = r.text
    # priority 50 (rent/housing) before priority 10 (albert heijn/groceries)
    assert body.index(">rent<") < body.index(">albert heijn<")


def test_sort_by_category_asc(client, seed):
    r = client.get("/rules?sort=category_asc")
    body = r.text
    # "food:groceries" sorts before "housing" alphabetically
    assert body.index("food:groceries") < body.index("housing")


def test_sort_by_category_desc(client, seed):
    r = client.get("/rules?sort=category_desc")
    body = r.text
    assert body.index("housing") < body.index("food:groceries")


def test_sort_by_match_value(client, seed):
    r = client.get("/rules?sort=match_value_asc")
    body = r.text
    # "albert heijn" < "rent" alphabetically
    assert body.index(">albert heijn<") < body.index(">rent<")


def test_sort_toggle_asc_desc_on_repeated_click(client, seed):
    # priority_asc is the default sort, so its own header link omits `sort=`
    # entirely (clean URL at the default) while still toggling to desc.
    r_asc = client.get("/rules?sort=priority_asc")
    assert "sort=priority_desc" in r_asc.text
    r_desc = client.get("/rules?sort=priority_desc")
    assert 'href="/rules"' in r_desc.text  # toggling back to default clears sort=


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def _form(**kw):
    base = dict(
        priority="100", rule_type="keyword", match_pattern="contains",
        field_target="description", match_value="coffee", category="Food:Coffee",
        tags="", notes="", is_active="on",
        filter_account="", filter_currency="", filter_date_from="", filter_date_to="",
    )
    base.update(kw)
    return base


def test_create_rule_persists_and_records_report(client, seed):
    factory, _ = seed
    r = client.post("/rules", data=_form(), follow_redirects=False)
    assert r.status_code == 303
    db = factory()
    rule = db.query(CategorizationRule).filter_by(match_value="coffee").one()
    assert rule.category == "food:coffee"  # normalized
    assert rule.uuid  # UUID assigned at creation
    db.close()
    reports = _reports(factory, "create")
    assert len(reports) == 1
    assert reports[0].rule_after["match_value"] == "coffee"
    assert reports[0].rule_before is None


def test_create_rule_redirect_carries_save_result_for_alert(client, seed):
    """Save gives no visible confirmation today — the fix redirects to
    /rules?saved=<id>&action=created&changed=<n>&report=<id> so the list
    page can render a success alert with the recategorization count."""
    factory, _ = seed
    r = client.post("/rules", data=_form(match_value="coffee", category="food:coffee"),
                    follow_redirects=False)
    assert r.status_code == 303
    location = r.headers["location"]
    assert location.startswith("/rules?saved=")
    assert "action=created" in location
    assert "changed=" in location
    assert "report=" in location

    # Following the redirect renders a dismissible success alert with the
    # matched rule id and a non-zero recategorized count (t2's "coffee"
    # description matches this rule per test_create_applies_rules_to_transactions).
    r2 = client.get(location)
    assert r2.status_code == 200
    assert 'id="rule-save-alert"' in r2.text
    assert "created" in r2.text
    assert "recategorized" in r2.text

    reports = _reports(factory, "create")
    report_id = reports[0].id
    assert f"report={report_id}" in location
    assert f"/rules/{reports[0].rule_id}/history#rule-report-{report_id}" in r2.text


def test_rules_list_without_saved_param_shows_no_alert(client, seed):
    r = client.get("/rules")
    assert r.status_code == 200
    assert 'id="rule-save-alert"' not in r.text


def test_create_applies_rules_to_transactions(client, seed):
    factory, _ = seed
    client.post("/rules", data=_form(match_value="coffee", category="food:coffee"))
    db = factory()
    # t4 is manual — must be untouched (Golden Principle 2)
    t4 = db.get(Transaction, "t4")
    assert t4.manual_category == "food:coffee" and t4.categorization_source == "manual"
    # t2 got matched by existing rent rule during reapply
    t2 = db.get(Transaction, "t2")
    assert t2.category == "housing"
    db.close()


def test_create_tag_only_rule_via_form(client, seed):
    factory, _ = seed
    data = _form(match_value="albert heijn", category="ignored-should-be-cleared",
                 tags="brand-ah", is_tag_only="on")
    r = client.post("/rules", data=data, follow_redirects=False)
    assert r.status_code == 303
    db = factory()
    rule = db.query(CategorizationRule).filter_by(match_value="albert heijn", is_tag_only=True).one()
    assert rule.is_tag_only is True
    assert rule.category is None
    assert rule.tags == "brand-ah"
    db.close()


def test_tag_only_rule_applies_to_manual_transaction_via_recategorize(client, seed):
    factory, _ = seed
    # t4 is manual (categorization_source == "manual").
    client.post("/rules", data=_form(
        match_value="coffee", category="", tags="drink", is_tag_only="on",
    ))
    db = factory()
    t4 = db.get(Transaction, "t4")
    assert t4.manual_category == "food:coffee"  # category untouched
    assert t4.tags == "drink"  # tag-only rule still applied
    db.close()


def test_rules_list_tag_only_tab_filters_rules(client, seed):
    client.post("/rules", data=_form(
        match_value="albert heijn", category="", tags="brand-ah", is_tag_only="on",
    ))
    r_active = client.get("/rules?tab=active")
    assert "housing" in r_active.text
    assert "brand-ah" not in r_active.text

    r_tag_only = client.get("/rules?tab=tag_only")
    assert "brand-ah" in r_tag_only.text
    assert "housing" not in r_tag_only.text


def test_create_with_conditions(client, seed):
    factory, _ = seed
    data = _form(match_value="sepa", category="transfers")
    data.update({
        "cond_field_target": ["description", "name"],
        "cond_match_pattern": ["contains", "exact"],
        "cond_match_value": ["iban", "j doe"],
        "cond_operator": ["AND", "OR"],
    })
    client.post("/rules", data=data)
    db = factory()
    rule = db.query(CategorizationRule).filter_by(match_value="sepa").one()
    assert len(rule.conditions) == 2
    assert rule.conditions[0].match_value == "iban"
    assert rule.conditions[0].operator == "AND"
    assert rule.conditions[1].operator == "OR"
    assert rule.conditions[1].sort_order == 1
    db.close()


def test_create_invalid_regex_shows_error_no_rule(client, seed):
    factory, _ = seed
    r = client.post("/rules", data=_form(match_pattern="regex", match_value="[unclosed"))
    assert r.status_code == 400
    assert "Invalid regex" in r.text
    db = factory()
    assert db.query(CategorizationRule).filter_by(match_value="[unclosed").count() == 0
    db.close()
    assert _reports(factory, "create") == []


def test_create_missing_required_field(client, seed):
    r = client.post("/rules", data=_form(match_value=""))
    assert r.status_code == 400


def test_create_invalid_rule_type(client, seed):
    r = client.post("/rules", data=_form(rule_type="bogus"))
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Update / toggle / delete
# ---------------------------------------------------------------------------


def test_update_rule_replaces_fields_and_conditions(client, seed):
    factory, (_, r2_id) = seed
    data = _form(match_value="rent payment", category="housing:rent", priority="40")
    data.update({
        "cond_field_target": ["description"],
        "cond_match_pattern": ["contains"],
        "cond_match_value": ["monthly"],
        "cond_operator": ["AND"],
    })
    r = client.post(f"/rules/{r2_id}", data=data, follow_redirects=False)
    assert r.status_code == 303
    db = factory()
    rule = db.get(CategorizationRule, r2_id)
    assert rule.match_value == "rent payment"
    assert rule.priority == 40
    assert [c.match_value for c in rule.conditions] == ["monthly"]
    db.close()
    reports = _reports(factory, "update")
    assert len(reports) == 1
    assert reports[0].rule_before["match_value"] == "rent"
    assert reports[0].rule_after["match_value"] == "rent payment"


def test_update_404(client, seed):
    r = client.post("/rules/9999", data=_form())
    assert r.status_code == 404


def test_toggle_records_report(client, seed):
    factory, (r1_id, _) = seed
    r = client.post(f"/rules/{r1_id}/toggle")
    assert r.status_code == 200
    db = factory()
    assert db.get(CategorizationRule, r1_id).is_active is False
    db.close()
    reports = _reports(factory, "toggle")
    assert len(reports) == 1
    assert reports[0].rule_before["is_active"] is True
    assert reports[0].rule_after["is_active"] is False
    # toggle back
    client.post(f"/rules/{r1_id}/toggle")
    db = factory()
    assert db.get(CategorizationRule, r1_id).is_active is True
    db.close()


def test_delete_records_report(client, seed):
    factory, (r1_id, _) = seed
    r = client.delete(f"/rules/{r1_id}")
    assert r.status_code == 200
    db = factory()
    assert db.get(CategorizationRule, r1_id) is None
    db.close()
    reports = _reports(factory, "delete")
    assert len(reports) == 1
    assert reports[0].rule_before["match_value"] == "albert heijn"
    assert reports[0].rule_after is None


def test_delete_404(client, seed):
    assert client.delete("/rules/9999").status_code == 404


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


def test_preview_draft_rule_shows_matches(client, seed):
    r = client.post("/rules/preview", data=_form(match_value="coffee"))
    assert r.status_code == 200
    assert "Coffee corner" not in r.text  # t4 is manual, excluded
    r = client.post("/rules/preview", data=_form(match_value="rent"))
    assert "Rent payment" in r.text
    assert "1" in r.text  # matched count


def test_preview_does_not_write(client, seed):
    factory, _ = seed
    client.post("/rules/preview", data=_form(match_value="rent", category="different"))
    db = factory()
    assert db.get(Transaction, "t2").category is None  # nothing applied
    assert db.query(CategorizationRule).count() == 2
    db.close()
    assert _reports(factory) == []


def test_preview_edit_shows_gains_losses(client, seed):
    factory, (r1_id, _) = seed
    # attribute t1 to rule 1 first
    db = factory()
    t1 = db.get(Transaction, "t1")
    t1.category, t1.categorization_source = "food:groceries", str(r1_id)
    db.commit()
    db.close()
    # draft edit: no longer matches albert heijn, now matches rent
    data = _form(match_value="rent", category="food:groceries")
    data["rule_id"] = str(r1_id)
    r = client.post("/rules/preview", data=data)
    assert r.status_code == 200
    assert "Lost" in r.text or "lost" in r.text
    assert "Gained" in r.text or "gained" in r.text
    assert "t1" in r.text  # lost transaction listed


def test_preview_invalid_regex_inline_error(client, seed):
    r = client.post("/rules/preview", data=_form(match_pattern="regex", match_value="[bad"))
    assert r.status_code == 200  # inline error, not a failure page
    assert "Invalid regex" in r.text


def test_preview_with_conditions(client, seed):
    data = _form(match_value="rent", category="housing")
    data.update({
        "cond_field_target": ["description"],
        "cond_match_pattern": ["contains"],
        "cond_match_value": ["nomatchhere"],
        "cond_operator": ["AND"],
    })
    r = client.post("/rules/preview", data=data)
    assert r.status_code == 200
    assert "Matched transactions (0)" in r.text  # AND condition filtered it out


# ---------------------------------------------------------------------------
# Editor pages + create-from-transaction
# ---------------------------------------------------------------------------


def test_new_rule_form(client, seed):
    r = client.get("/rules/new")
    assert r.status_code == 200
    for name in ("priority", "rule_type", "match_pattern", "match_value",
                 "category", "tags", "notes", "filter_account", "filter_currency",
                 "filter_date_from", "filter_date_to"):
        assert f'name="{name}"' in r.text


def test_edit_form_shows_rule_and_conditions(client, seed):
    _, (_, r2_id) = seed
    r = client.get(f"/rules/{r2_id}/edit")
    assert r.status_code == 200
    assert 'value="rent"' in r.text
    assert "landlord" in r.text  # condition serialized into the editor


def test_edit_404(client, seed):
    assert client.get("/rules/9999/edit").status_code == 404


def test_rule_id_redirects_to_edit(client, seed):
    _, (r1_id, _) = seed
    r = client.get(f"/rules/{r1_id}", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert r.headers["location"].endswith(f"/rules/{r1_id}/edit")


def _match_state(html: str) -> dict:
    """Return the initial state of the ruleMatch Alpine component on the page."""
    m = re.search(r"ruleMatch\((.*?)\)'", html, re.S)
    assert m, "the page holds no Match card"
    return json.loads(m.group(1))


def _selected_fields(state: dict) -> list[str]:
    return [r["field"] for r in state["rows"] if r["selected"]]


def test_from_transaction_prefills_structured(client, seed):
    r = client.get("/rules/new?from_transaction=t1")
    assert r.status_code == 200
    state = _match_state(r.text)
    assert _selected_fields(state) == ["merchant_name"]
    row = state["rows"][0]
    assert (row["value"], row["pattern"]) == ("ALBERT HEIJN", "contains")
    assert state["filters"]["account"] == {"on": True, "value": "NL01"}
    assert state["filters"]["currency"] == {"on": False, "value": "EUR"}
    assert 'name="sample_transaction_id" value="t1"' in r.text


def test_from_transaction_prefills_iban(client, seed):
    r = client.get("/rules/new?from_transaction=t3")
    assert r.status_code == 200
    state = _match_state(r.text)
    assert _selected_fields(state) == ["iban"]
    assert state["rows"][0]["value"] == "NL91ABNA0417164300"


def test_from_transaction_shows_all_fields(client, seed):
    state = _match_state(client.get("/rules/new?from_transaction=t3").text)
    assert [r["field"] for r in state["rows"]] == ["iban", "description"]


def test_from_transaction_auto_preview_marker(client, seed):
    r = client.get("/rules/new?from_transaction=t2")
    assert "data-auto-preview" in r.text  # the Match card fires the first preview
    assert "rule-auto-preview from:body" in r.text


def test_edit_has_no_auto_preview(client, seed):
    _, (r1_id, _) = seed
    assert "data-auto-preview" not in client.get(f"/rules/{r1_id}/edit").text


def test_edit_shows_no_field_list(client, seed):
    _, (_, r2_id) = seed
    r = client.get(f"/rules/{r2_id}/edit")
    state = _match_state(r.text)
    assert state["rows"] == []
    assert 'name="sample_transaction_id"' not in r.text
    # The saved primary match stays in the classic inputs.
    assert 'name="match_value" class="form-control"' in r.text
    assert 'value="rent"' in r.text
    assert [c["match_value"] for c in state["conditions"]] == ["landlord"]
    assert state["filters"]["account"] == {"on": False, "value": ""}


def test_edit_shows_saved_filters_as_selected_rows(client, seed):
    factory, (r1_id, _) = seed
    db = factory()
    rule = db.get(CategorizationRule, r1_id)
    rule.filter_currency = "USD"
    rule.filter_date_from = date(2024, 1, 1)
    db.commit()
    db.close()
    state = _match_state(client.get(f"/rules/{r1_id}/edit").text)
    assert state["filters"]["currency"] == {"on": True, "value": "USD"}
    assert state["filters"]["date_from"] == {"on": True, "value": "2024-01-01"}
    assert state["filters"]["date_to"] == {"on": False, "value": ""}


def test_sample_returns_match_card_for_edit_draft(client, seed):
    factory, (_, r2_id) = seed
    before = len(_reports(factory))
    form = {
        "rule_id": str(r2_id), "rule_type": "keyword", "match_pattern": "exact",
        "field_target": "description", "match_value": "rent",
        "category": "housing", "priority": "50", "is_active": "1",
        "cond_field_target": "description", "cond_match_pattern": "contains",
        "cond_match_value": "landlord", "cond_operator": "AND", "cond_sort_order": "0",
        "use_sample_id": "t1",
    }
    r = client.post("/rules/sample", data=form)
    assert r.status_code == 200
    assert r.headers["HX-Trigger-After-Settle"] == "rule-sample-loaded"
    assert 'id="match-card"' in r.text
    assert "Assign" not in r.text  # only the Match card
    state = _match_state(r.text)
    desc = next(row for row in state["rows"] if row["field"] == "description")
    assert desc == {"field": "description", "value": "rent", "pattern": "exact",
                    "selected": True, "in_sample": True}
    assert _selected_fields(state) == ["description"]
    # The second condition on description stays in the advanced builder.
    assert [c["match_value"] for c in state["conditions"]] == ["landlord"]
    # A filter that the draft does not use takes the value of the sample.
    assert state["filters"]["account"] == {"on": False, "value": "NL01"}
    assert len(_reports(factory)) == before  # writes nothing


def test_sample_unknown_transaction_404(client, seed):
    r = client.post("/rules/sample", data={"use_sample_id": "nope", "match_value": "x"})
    assert r.status_code == 404


def test_save_from_field_rows_form(client, seed):
    """The form shape that the selected rows post saves the expected rule."""
    factory, _ = seed
    form = {
        "sample_transaction_id": "t1", "rule_type": "keyword",
        "field_target": "merchant_name", "match_pattern": "exact",
        "match_value": "ALBERT HEIJN",
        # One row condition (AND), then one advanced condition (OR).
        "cond_field_target": ["description", "description"],
        "cond_match_pattern": ["contains", "contains"],
        "cond_match_value": ["groceries", "jumbo"],
        "cond_operator": ["AND", "OR"],
        "cond_sort_order": ["0", "1"],
        "filter_account": "NL01", "category": "food:ah", "priority": "5",
        "is_active": "1",
    }
    r = client.post("/rules", data=form, follow_redirects=False)
    assert r.status_code == 303
    db = factory()
    rule = db.query(CategorizationRule).filter_by(category="food:ah").one()
    assert (rule.field_target, rule.match_pattern, rule.match_value) == (
        "merchant_name", "exact", "ALBERT HEIJN")
    assert rule.filter_account == "NL01"
    assert rule.filter_currency is None
    assert [(c.field_target, c.match_value, c.operator) for c in rule.conditions] == [
        ("description", "groceries", "AND"), ("description", "jumbo", "OR")]
    assert db.get(Transaction, "t1").category == "food:ah"
    db.close()


def test_save_with_no_selected_field_asks_for_one(client, seed):
    r = client.post("/rules", data={
        "sample_transaction_id": "t1", "rule_type": "keyword", "field_target": "",
        "match_pattern": "contains", "match_value": "", "category": "x",
    })
    assert r.status_code == 400
    assert "Select at least one field." in r.text
    # The re-rendered editor keeps the field list of the sample.
    assert [row["field"] for row in _match_state(r.text)["rows"]][0] == "merchant_name"


def test_preview_with_no_selected_field_asks_for_one(client, seed):
    r = client.post("/rules/preview", data={
        "sample_transaction_id": "t1", "rule_type": "keyword", "field_target": "",
        "match_pattern": "contains", "match_value": "",
    })
    assert r.status_code == 200
    assert "Select at least one field." in r.text


def test_preview_rows_offer_use_as_sample(client, seed):
    r = client.post("/rules/preview", data={
        "rule_type": "keyword", "field_target": "description",
        "match_pattern": "contains", "match_value": "albert",
    })
    assert "Use as sample" in r.text
    assert "&#34;use_sample_id&#34;: &#34;t1&#34;" in r.text or '"use_sample_id": "t1"' in r.text


def test_from_transaction_unknown_id_404(client, seed):
    assert client.get("/rules/new?from_transaction=nope").status_code == 404


# ---------------------------------------------------------------------------
# History + recategorize
# ---------------------------------------------------------------------------


def test_history_lists_reports_newest_first(client, seed):
    factory, (r1_id, _) = seed
    client.post("/rules", data=_form(match_value="first", category="a"))
    client.post(f"/rules/{r1_id}/toggle")
    r = client.get("/rules/history")
    assert r.status_code == 200
    assert r.text.index("toggle") < r.text.index("create")


def test_history_shows_transaction_diffs(client, seed):
    client.post("/rules", data=_form(match_value="coffee", category="food:coffee"))
    # creating the coffee rule triggers reapply: t1 (albert heijn) + t2 (rent) get
    # categorized by the seed rules for the first time -> items in the report
    r = client.get("/rules/history")
    assert "t2" in r.text
    assert "housing" in r.text


def test_history_shows_before_after_diff_on_update(client, seed):
    _, (_, r2_id) = seed
    client.post(f"/rules/{r2_id}", data=_form(match_value="rent NEW", category="housing"))
    r = client.get("/rules/history")
    assert "rent NEW" in r.text


def test_per_rule_history(client, seed):
    factory, (r1_id, r2_id) = seed
    client.post(f"/rules/{r1_id}/toggle")
    client.post(f"/rules/{r2_id}/toggle")
    r = client.get(f"/rules/{r1_id}/history")
    assert r.status_code == 200
    assert f"#{r1_id}" in r.text
    # only rule 1's report present
    db = factory()
    n = db.query(RuleChangeReport).filter(RuleChangeReport.rule_id == r2_id).count()
    db.close()
    assert n == 1
    assert f"/rules/{r2_id}/history" not in r.text


def test_recategorize_all(client, seed):
    factory, _ = seed
    r = client.post("/rules/recategorize", follow_redirects=False)
    assert r.status_code == 200
    assert "rulesChanged" in r.headers.get("HX-Trigger", "")
    reports = _reports(factory, "recategorize")
    assert len(reports) == 1
    # t1 + t2 newly categorized by the seed rules
    assert reports[0].summary["changed"] == 2
    db = factory()
    assert db.get(Transaction, "t1").category == "food:groceries"
    assert db.get(Transaction, "t1").tags == "ah"
    db.close()


def test_recategorize_preserves_manual(client, seed):
    factory, _ = seed
    client.post("/rules/recategorize")
    db = factory()
    t4 = db.get(Transaction, "t4")
    assert t4.manual_category == "food:coffee"
    assert t4.category is None
    db.close()


def test_editor_assets_carry_a_version(client, seed):
    """A new version in the URL stops a browser from using an old rules.js."""
    r = client.get("/rules/new")
    assert re.search(r'src="/static/js/rules\.js\?v=\d+"', r.text)
    assert re.search(r'href="/static/rules\.css\?v=\d+"', r.text)
