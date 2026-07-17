"""Generate rule-engine parity fixtures: match outcomes + two-pass apply_rules
results from the real Python implementation (in-memory SQLite)."""
import json
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from abn_combined.core.models import (
    Base, CategorizationRule, RuleCondition, Transaction,
)
from abn_combined.core.categorizer import _apply_rule_to_transaction, apply_rules


class DraftCond:
    def __init__(self, field_target, match_pattern, match_value, operator="AND", sort_order=0):
        self.field_target = field_target
        self.match_pattern = match_pattern
        self.match_value = match_value
        self.operator = operator
        self.sort_order = sort_order


class DraftRule:
    def __init__(self, **kw):
        self.rule_type = kw.get("rule_type", "full_description")
        self.match_pattern = kw.get("match_pattern", "contains")
        self.field_target = kw.get("field_target", "description")
        self.match_value = kw["match_value"]
        self.conditions = kw.get("conditions", [])
        self.filter_account = kw.get("filter_account")
        self.filter_currency = kw.get("filter_currency")
        self.filter_date_from = kw.get("filter_date_from")
        self.filter_date_to = kw.get("filter_date_to")


TXNS = [
    {"description": "BEA, Betaalpas Albert Heijn 1234,PAS123", "description_structured": None,
     "accountNumber": "NL91", "currency": "EUR", "transactiondate": date(2026, 1, 15)},
    {"description": "SEPA Overboeking IBAN: NL91ABNA0417164300 Naam: J Doe", "description_structured": json.dumps({"iban": "NL91ABNA0417164300", "name": "J Doe", "recurring": True}),
     "accountNumber": "NL91", "currency": "EUR", "transactiondate": date(2026, 2, 1)},
    {"description": "WERO/Payment To John", "description_structured": None,
     "accountNumber": "NL02", "currency": "USD", "transactiondate": date(2025, 6, 1)},
    {"description": "Netflix subscription 12.99", "description_structured": json.dumps({"merchant": "Netflix", "kind": "subscription"}),
     "accountNumber": "NL91", "currency": "EUR", "transactiondate": date(2026, 3, 10)},
]

RULES = [
    ("contains_desc", DraftRule(match_value="albert heijn")),
    ("exact_norm", DraftRule(match_pattern="exact", match_value="WERO/Payment To John")),
    ("starts_with", DraftRule(match_pattern="starts_with", match_value="BEA, Betaalpas")),
    ("ends_with", DraftRule(match_pattern="ends_with", match_value="pas123")),
    ("regex_ok", DraftRule(match_pattern="regex", match_value=r"albert\s*heijn")),
    ("regex_on_normalized", DraftRule(match_pattern="regex", match_value=r"albert heijn")),
    ("regex_invalid", DraftRule(match_pattern="regex", match_value=r"([")),
    ("structured_field", DraftRule(rule_type="structured_field", field_target="merchant", match_pattern="exact", match_value="netflix")),
    ("structured_bool", DraftRule(rule_type="structured_field", field_target="recurring", match_pattern="exact", match_value="true")),
    ("structured_missing", DraftRule(rule_type="structured_field", field_target="nope", match_pattern="contains", match_value="x")),
    ("iban_exact", DraftRule(rule_type="account_iban", field_target="iban", match_pattern="exact", match_value="NL91ABNA0417164300")),
    ("iban_ends", DraftRule(rule_type="account_iban", field_target="iban", match_pattern="ends_with", match_value="4300")),
    ("iban_from_desc_regex", DraftRule(rule_type="account_iban", field_target="iban", match_pattern="contains", match_value="ABNA")),
    ("iban_desc_target", DraftRule(rule_type="account_iban", field_target="description", match_pattern="contains", match_value="overboeking")),
    ("cond_and_true", DraftRule(match_value="netflix", conditions=[DraftCond("kind", "exact", "subscription")])),
    ("cond_and_false", DraftRule(match_value="netflix", conditions=[DraftCond("kind", "exact", "movie")])),
    ("cond_or_rescue", DraftRule(match_value="netflix", conditions=[DraftCond("kind", "exact", "movie"), DraftCond("merchant", "contains", "net", "OR", 1)])),
    ("filter_account_match", DraftRule(match_value="albert", filter_account="NL91")),
    ("filter_account_miss", DraftRule(match_value="albert", filter_account="NL02")),
    ("filter_currency", DraftRule(match_value="payment", filter_currency="USD")),
    ("filter_date_window", DraftRule(match_value="albert", filter_date_from=date(2026, 1, 1), filter_date_to=date(2026, 1, 31))),
    ("filter_date_excludes", DraftRule(match_value="netflix", filter_date_to=date(2026, 2, 28))),
    ("no_structured_no_field", DraftRule(field_target="merchant", match_value="netflix")),
]

matrix = []
for name, rule in RULES:
    row = {"rule": name, "matches": []}
    for i, t in enumerate(TXNS):
        row["matches"].append(bool(_apply_rule_to_transaction(rule, t)))
    matrix.append(row)

# ---- two-pass apply_rules scenario ----
engine = create_engine("sqlite://")
Base.metadata.create_all(engine)
db = Session(engine)

txn_rows = [
    Transaction(id="t1", accountNumber="NL91", transactiondate=date(2026, 1, 15), amount=-12.30,
                description="BEA, Betaalpas Albert Heijn 1234,PAS123", currency="EUR"),
    Transaction(id="t2", accountNumber="NL91", transactiondate=date(2026, 2, 1), amount=-50,
                description="Netflix subscription", currency="EUR"),
    Transaction(id="t3", accountNumber="NL91", transactiondate=date(2026, 2, 2), amount=-5,
                description="Netflix subscription extra", currency="EUR",
                manual_category="entertainment-manual", manual_tags="keep",
                categorization_source="manual", category="old-cat", tags="old-tag"),
    Transaction(id="t4", accountNumber="NL91", transactiondate=date(2026, 2, 3), amount=-9,
                description="nothing matches me", currency="EUR", category="stale", tags="staletag",
                categorization_source="99"),
]
for r in txn_rows:
    db.add(r)

rules_rows = [
    CategorizationRule(id=1, uuid="u1", priority=10, rule_type="full_description",
                       match_pattern="contains", field_target="description",
                       match_value="albert heijn", category="Groceries-AH", tags="food",
                       is_active=True, is_tag_only=False),
    CategorizationRule(id=2, uuid="u2", priority=20, rule_type="full_description",
                       match_pattern="contains", field_target="description",
                       match_value="netflix", category="entertainment", tags=None,
                       is_active=True, is_tag_only=False),
    CategorizationRule(id=3, uuid="u3", priority=5, rule_type="full_description",
                       match_pattern="contains", field_target="description",
                       match_value="netflix", category="should-not-win-inactive",
                       is_active=False, is_tag_only=False),
    CategorizationRule(id=4, uuid="u4", priority=100, rule_type="full_description",
                       match_pattern="contains", field_target="description",
                       match_value="subscription", category=None, tags="recurring,large",
                       is_active=True, is_tag_only=True),
    CategorizationRule(id=5, uuid="u5", priority=100, rule_type="full_description",
                       match_pattern="contains", field_target="description",
                       match_value="netflix", category=None, tags="recurring,video",
                       is_active=True, is_tag_only=True),
]
for r in rules_rows:
    db.add(r)
db.commit()

changes = apply_rules(db)
result = {
    "changes": sorted(
        [{"id": c.transaction_id, "old_category": c.old_category, "new_category": c.new_category,
          "old_tags": c.old_tags, "new_tags": c.new_tags} for c in changes],
        key=lambda c: c["id"],
    ),
    "final": [],
}
for t in db.query(Transaction).order_by(Transaction.id).all():
    result["final"].append({
        "id": t.id, "category": t.category, "manual_category": t.manual_category,
        "tags": t.tags, "manual_tags": t.manual_tags,
        "categorization_source": t.categorization_source,
    })

out = {"match_matrix": {"transactions": [
    {k: (v.isoformat() if isinstance(v, date) else v) for k, v in t.items()} for t in TXNS
], "rules": matrix}, "apply_rules_scenario": result}

with open("rule_parity.json", "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(json.dumps(out["apply_rules_scenario"], indent=2))
print("match matrix rows:", len(matrix))
