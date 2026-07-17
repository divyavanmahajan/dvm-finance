"""Generate a snapshot fixture with the real Python exporter, plus the
expected import counts when importing it into a half-overlapping DB."""
import json
import gzip
import shutil
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from abn_combined.core.models import (
    Base, Budget, CategorizationRule, RuleCondition, Transaction,
)
from abn_combined.core.categorizer import record_rule_change, rule_snapshot
from abn_combined.core.snapshots import export_snapshot, import_snapshot

work = Path("snapfix")
if work.exists():
    shutil.rmtree(work)
(work / "src").mkdir(parents=True)
(work / "dst").mkdir(parents=True)

# --- source DB (the "desktop" machine) ---
src_engine = create_engine(f"sqlite:///{work/'src'/'abn_combined.db'}")
Base.metadata.create_all(src_engine)
src = Session(src_engine)

src.add_all([
    Transaction(id="t1", accountNumber="NL91", transactiondate=date(2026, 1, 15),
                amount=-12.30, description="BEA Albert Heijn", currency="EUR",
                category="groceries-ah", tags="food", categorization_source="1",
                startsaldo=1000.00, endsaldo=987.70, valuedate=date(2026, 1, 15),
                description_structured=json.dumps({"merchant": "Albert Heijn"}),
                transaction_hash="abc", source_file="jan.sta", source_line=3),
    Transaction(id="t2", accountNumber="NL91", transactiondate=date(2026, 2, 1),
                amount=-50, description="Netflix", currency="EUR",
                manual_category="entertainment", manual_tags="fun",
                categorization_source="manual"),
    Transaction(id="t3", accountNumber="NL02", transactiondate=date(2026, 2, 5),
                amount=200, description="Salary", currency="EUR"),
])
rule1 = CategorizationRule(id=1, uuid="11111111-1111-1111-1111-111111111111",
                           priority=10, rule_type="full_description",
                           match_pattern="contains", field_target="description",
                           match_value="albert heijn", category="groceries-ah",
                           tags="food", is_active=True, is_tag_only=False,
                           notes="ah rule",
                           conditions=[RuleCondition(field_target="merchant",
                                                     match_pattern="contains",
                                                     match_value="albert",
                                                     operator="AND", sort_order=0)])
rule2 = CategorizationRule(id=2, uuid="22222222-2222-2222-2222-222222222222",
                           priority=100, rule_type="full_description",
                           match_pattern="contains", field_target="description",
                           match_value="subscription", category=None,
                           tags="recurring", is_active=True, is_tag_only=True)
src.add_all([rule1, rule2])
src.add(Budget(category="groceries", amount=400, period="monthly",
               start_date=date(2026, 1, 1), notes="grocery budget"))
src.commit()
record_rule_change(src, "create", before=None, after=rule_snapshot(rule1),
                   rule_id=1, rule_uuid=rule1.uuid)

snap_path = export_snapshot(src, work / "src")
print("snapshot:", snap_path)

# --- destination DB (the "phone", half-overlapping) ---
dst_engine = create_engine(f"sqlite:///{work/'dst'/'abn_combined.db'}")
Base.metadata.create_all(dst_engine)
dst = Session(dst_engine)
dst.add_all([
    # t1 exists locally with DIFFERENT manual category -> incoming wins overwrite
    Transaction(id="t1", accountNumber="NL91", transactiondate=date(2026, 1, 15),
                amount=-12.30, description="BEA Albert Heijn", currency="EUR",
                manual_category="local-manual", categorization_source="manual"),
    # t-local only exists locally -> must survive
    Transaction(id="t-local", accountNumber="NL91", transactiondate=date(2026, 3, 1),
                amount=-1, description="local only", currency="EUR"),
])
# same rule uuid, different local integer id -> categorization_source remap target
dst.add(CategorizationRule(id=7, uuid="11111111-1111-1111-1111-111111111111",
                           priority=99, rule_type="full_description",
                           match_pattern="contains", field_target="description",
                           match_value="old value", category="old-cat",
                           is_active=False, is_tag_only=False))
dst.commit()

from abn_combined.core.snapshots import read_snapshot
snapshot_doc = read_snapshot(snap_path.read_bytes())
report = import_snapshot(dst, snapshot_doc, work / "dst" / "abn_combined.db")
print(json.dumps({"counts": report.counts, "overwrites": report.overwrites},
                 indent=2, default=str))

final = {
    "transactions": [
        {"id": t.id, "category": t.category, "manual_category": t.manual_category,
         "tags": t.tags, "manual_tags": t.manual_tags,
         "categorization_source": t.categorization_source}
        for t in dst.query(Transaction).order_by(Transaction.id)
    ],
    "rules": [
        {"id": r.id, "uuid": r.uuid, "priority": r.priority,
         "match_value": r.match_value, "category": r.category,
         "is_active": r.is_active, "n_conditions": len(r.conditions)}
        for r in dst.query(CategorizationRule).order_by(CategorizationRule.uuid)
    ],
}
print(json.dumps(final, indent=2))

# save artifacts
shutil.copy(snap_path, "fixture-snapshot.json.gz")
with open("fixture-snapshot-expected.json", "w") as f:
    json.dump({"import_counts": report.counts, "overwrites": report.overwrites,
               "final_state": final}, f, indent=2, default=str)
with gzip.open("fixture-snapshot.json.gz") as f:
    doc = json.load(f)
print("header:", doc["header"])
print("sections:", {k: len(v) for k, v in doc.items() if k != "header"})
EOF_MARKER_NOT_NEEDED = None
