"""Snapshot export/import service tests (step 11, FR9).

Covers the merge matrix (new / identical / conflicting per entity), incoming-wins
semantics including manual categorizations, local-only preservation, rejection of
version mismatches and corrupt files, pre-import backup, transactionality, and a
full export→import round trip into a fresh database.
"""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from abn_combined.core import snapshots as snap_mod
from abn_combined.core.models import (
    Base,
    Budget,
    CategorizationRule,
    RuleChangeItem,
    RuleChangeReport,
    RuleCondition,
    SnapshotImport,
    Transaction,
)
from abn_combined.core.snapshots import (
    SCHEMA_VERSION,
    SnapshotError,
    build_snapshot,
    export_snapshot,
    import_snapshot,
    list_exports,
    read_snapshot,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers: two independent sqlite databases (machine A and B)
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path, name: str) -> tuple[Session, Path]:
    data_dir = tmp_path / name
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "abn_combined.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return session, db_path


@pytest.fixture
def db_a(tmp_path):
    session, db_path = _make_db(tmp_path, "machine_a")
    yield session, db_path
    session.close()


@pytest.fixture
def db_b(tmp_path):
    session, db_path = _make_db(tmp_path, "machine_b")
    yield session, db_path
    session.close()


def make_txn(txn_id: str = "t1", **kw) -> Transaction:
    defaults = dict(
        id=txn_id,
        accountNumber="NL01TEST0123456789",
        transactiondate=date(2026, 1, 15),
        amount=Decimal("-42.50"),
        description=f"Test payment {txn_id}",
        currency="EUR",
    )
    defaults.update(kw)
    return Transaction(**defaults)


def make_rule(rule_uuid: str = "00000000-0000-0000-0000-000000000001", **kw):
    defaults = dict(
        uuid=rule_uuid,
        priority=100,
        rule_type="keyword",
        match_pattern="contains",
        field_target="description",
        match_value="albert heijn",
        category="groceries",
        is_active=True,
    )
    defaults.update(kw)
    return CategorizationRule(**defaults)


def make_budget(**kw) -> Budget:
    defaults = dict(
        category="groceries",
        amount=Decimal("400.00"),
        period="month",
        start_date=date(2026, 1, 1),
    )
    defaults.update(kw)
    return Budget(**defaults)


def _export_bytes(db: Session, data_dir: Path) -> dict:
    path = export_snapshot(db, data_dir)
    return read_snapshot(path.read_bytes())


# ---------------------------------------------------------------------------
# Export format
# ---------------------------------------------------------------------------


def test_export_writes_versioned_gzip_json(db_a):
    db, db_path = db_a
    db.add(make_txn("t1"))
    db.commit()

    path = export_snapshot(db, db_path.parent)
    assert path.exists()
    assert path.parent == db_path.parent / "snapshots"
    assert path.name.endswith(".json.gz")

    payload = json.loads(gzip.decompress(path.read_bytes()))
    header = payload["header"]
    assert header["schema_version"] == SCHEMA_VERSION
    assert header["exported_at"]
    assert header["machine_id"]
    assert {"transactions", "rules", "budgets", "rule_change_reports"} <= set(payload)


def test_export_includes_all_transaction_columns(db_a):
    db, db_path = db_a
    db.add(
        make_txn(
            "t1",
            manual_category="dining",
            manual_tags="friends",
            categorization_source="manual",
            tags="auto-tag",
            description_structured='{"name": "cafe"}',
        )
    )
    db.commit()
    payload = _export_bytes(db, db_path.parent)
    txn = payload["transactions"][0]
    for col in (
        "id", "accountNumber", "transactiondate", "amount", "description",
        "category", "manual_category", "tags", "manual_tags",
        "categorization_source", "currency", "description_structured",
    ):
        assert col in txn
    assert txn["manual_category"] == "dining"
    assert txn["categorization_source"] == "manual"


def test_export_rules_keyed_by_uuid_with_conditions(db_a):
    db, db_path = db_a
    rule = make_rule()
    rule.conditions.append(
        RuleCondition(field_target="name", match_pattern="contains",
                      match_value="ah", operator="AND", sort_order=0)
    )
    db.add(rule)
    db.commit()
    payload = _export_bytes(db, db_path.parent)
    (r,) = payload["rules"]
    assert r["uuid"] == rule.uuid
    assert r["conditions"][0]["match_value"] == "ah"


def test_machine_id_is_stable_per_data_dir(db_a):
    db, db_path = db_a
    p1 = _export_bytes(db, db_path.parent)
    p2 = _export_bytes(db, db_path.parent)
    assert p1["header"]["machine_id"] == p2["header"]["machine_id"]


def test_list_exports(db_a):
    db, db_path = db_a
    assert list_exports(db_path.parent) == []
    path = export_snapshot(db, db_path.parent)
    (entry,) = list_exports(db_path.parent)
    assert entry["name"] == path.name
    assert entry["size"] > 0
    assert isinstance(entry["modified"], datetime)


# ---------------------------------------------------------------------------
# Validation: version mismatch + corrupt files
# ---------------------------------------------------------------------------


def test_read_snapshot_rejects_schema_version_mismatch():
    payload = {"header": {"schema_version": 99, "exported_at": "x", "machine_id": "m"},
               "transactions": [], "rules": [], "budgets": [], "rule_change_reports": []}
    blob = gzip.compress(json.dumps(payload).encode())
    with pytest.raises(SnapshotError, match="[Ss]chema version"):
        read_snapshot(blob)


def test_read_snapshot_rejects_corrupt_gzip():
    with pytest.raises(SnapshotError):
        read_snapshot(b"not gzip at all")


def test_read_snapshot_rejects_corrupt_json():
    with pytest.raises(SnapshotError):
        read_snapshot(gzip.compress(b"{ not json"))


def test_read_snapshot_rejects_missing_header():
    blob = gzip.compress(json.dumps({"transactions": []}).encode())
    with pytest.raises(SnapshotError):
        read_snapshot(blob)


# ---------------------------------------------------------------------------
# Merge matrix: transactions
# ---------------------------------------------------------------------------


def test_new_transaction_inserted(db_a, db_b):
    (a, a_path), (b, b_path) = db_a, db_b
    a.add(make_txn("t1", category="groceries"))
    a.commit()
    snap = _export_bytes(a, a_path.parent)

    report = import_snapshot(b, snap, b_path)
    assert report.counts["transactions"]["inserted"] == 1
    txn = b.get(Transaction, "t1")
    assert txn is not None
    assert txn.category == "groceries"


def test_identical_transaction_unchanged(db_a, db_b):
    (a, a_path), (b, b_path) = db_a, db_b
    a.add(make_txn("t1"))
    b.add(make_txn("t1"))
    a.commit()
    b.commit()
    snap = _export_bytes(a, a_path.parent)

    report = import_snapshot(b, snap, b_path)
    assert report.counts["transactions"]["unchanged"] == 1
    assert report.counts["transactions"]["inserted"] == 0
    assert report.counts["transactions"]["updated"] == 0


def test_conflicting_manual_category_incoming_wins(db_a, db_b):
    """Snapshot import is the only path allowed to overwrite manual edits (GP2)."""
    (a, a_path), (b, b_path) = db_a, db_b
    a.add(make_txn("t1", manual_category="dining", manual_tags="a-tags",
                   categorization_source="manual"))
    b.add(make_txn("t1", manual_category="groceries", manual_tags="b-tags",
                   categorization_source="manual"))
    a.commit()
    b.commit()
    snap = _export_bytes(a, a_path.parent)

    report = import_snapshot(b, snap, b_path)
    b.expire_all()
    txn = b.get(Transaction, "t1")
    assert txn.manual_category == "dining"
    assert txn.manual_tags == "a-tags"
    assert report.counts["transactions"]["updated"] == 1
    # The overwritten locally-differing item is listed in the report.
    overwrites = report.overwrites["transactions"]
    assert overwrites[0]["id"] == "t1"
    assert "manual_category" in overwrites[0]["fields"]


def test_local_only_transaction_preserved(db_a, db_b):
    (a, a_path), (b, b_path) = db_a, db_b
    a.add(make_txn("t1"))
    b.add(make_txn("b-only"))
    a.commit()
    b.commit()
    snap = _export_bytes(a, a_path.parent)

    import_snapshot(b, snap, b_path)
    assert b.get(Transaction, "b-only") is not None
    assert b.get(Transaction, "t1") is not None


# ---------------------------------------------------------------------------
# Merge matrix: rules (identity by uuid)
# ---------------------------------------------------------------------------


def test_new_rule_inserted_by_uuid(db_a, db_b):
    (a, a_path), (b, b_path) = db_a, db_b
    rule = make_rule()
    rule.conditions.append(
        RuleCondition(field_target="name", match_pattern="exact",
                      match_value="ah", operator="OR", sort_order=0)
    )
    a.add(rule)
    a.commit()
    snap = _export_bytes(a, a_path.parent)

    report = import_snapshot(b, snap, b_path)
    assert report.counts["rules"]["inserted"] == 1
    local = b.query(CategorizationRule).filter_by(uuid=rule.uuid).one()
    assert local.category == "groceries"
    assert local.conditions[0].operator == "OR"


def test_conflicting_rule_incoming_wins_and_conditions_replaced(db_a, db_b):
    (a, a_path), (b, b_path) = db_a, db_b
    uu = "00000000-0000-0000-0000-00000000abcd"
    a_rule = make_rule(uu, category="dining", match_value="cafe", priority=5)
    a_rule.conditions.append(
        RuleCondition(field_target="name", match_pattern="contains",
                      match_value="incoming-cond", operator="AND", sort_order=0)
    )
    a.add(a_rule)
    b_rule = make_rule(uu, category="groceries", match_value="cafe", priority=50)
    b_rule.conditions.append(
        RuleCondition(field_target="name", match_pattern="contains",
                      match_value="local-cond", operator="AND", sort_order=0)
    )
    b.add(b_rule)
    a.commit()
    b.commit()
    snap = _export_bytes(a, a_path.parent)

    report = import_snapshot(b, snap, b_path)
    b.expire_all()
    local = b.query(CategorizationRule).filter_by(uuid=uu).one()
    assert local.category == "dining"
    assert local.priority == 5
    assert [c.match_value for c in local.conditions] == ["incoming-cond"]
    assert report.counts["rules"]["updated"] == 1
    assert report.overwrites["rules"][0]["uuid"] == uu


def test_identical_rule_unchanged_and_local_only_rule_preserved(db_a, db_b):
    (a, a_path), (b, b_path) = db_a, db_b
    uu = "00000000-0000-0000-0000-000000000002"
    a.add(make_rule(uu))
    b.add(make_rule(uu))
    b.add(make_rule("00000000-0000-0000-0000-00000000b0b0", match_value="b only"))
    a.commit()
    b.commit()
    snap = _export_bytes(a, a_path.parent)

    report = import_snapshot(b, snap, b_path)
    assert report.counts["rules"]["unchanged"] == 1
    assert b.query(CategorizationRule).count() == 2


def test_categorization_source_remapped_to_local_rule_id(db_a, db_b):
    """Incoming rule ids differ per machine; sources are remapped via rule uuid."""
    (a, a_path), (b, b_path) = db_a, db_b
    # Occupy id 1 on B with an unrelated rule so ids diverge.
    b.add(make_rule("00000000-0000-0000-0000-00000000feed", match_value="unrelated"))
    b.commit()
    uu = "00000000-0000-0000-0000-000000000003"
    a_rule = make_rule(uu)
    a.add(a_rule)
    a.flush()
    a.add(make_txn("t1", category="groceries", categorization_source=str(a_rule.id)))
    a.commit()
    snap = _export_bytes(a, a_path.parent)

    import_snapshot(b, snap, b_path)
    local_rule = b.query(CategorizationRule).filter_by(uuid=uu).one()
    txn = b.get(Transaction, "t1")
    assert txn.categorization_source == str(local_rule.id)


# ---------------------------------------------------------------------------
# Merge matrix: budgets (identity by category+period+start_date)
# ---------------------------------------------------------------------------


def test_budget_new_identical_conflicting(db_a, db_b):
    (a, a_path), (b, b_path) = db_a, db_b
    a.add(make_budget())  # conflicting with B's (different amount)
    a.add(make_budget(category="transport", amount=Decimal("120.00")))  # new for B
    a.add(make_budget(category="rent", amount=Decimal("1500.00")))  # identical on both
    b.add(make_budget(amount=Decimal("999.00")))
    b.add(make_budget(category="rent", amount=Decimal("1500.00")))
    b.add(make_budget(category="b-only", amount=Decimal("10.00")))  # local-only
    a.commit()
    b.commit()
    snap = _export_bytes(a, a_path.parent)

    report = import_snapshot(b, snap, b_path)
    b.expire_all()
    assert report.counts["budgets"] == {"inserted": 1, "updated": 1, "unchanged": 1}
    groceries = b.query(Budget).filter_by(category="groceries").one()
    assert groceries.amount == Decimal("400.00")  # incoming wins
    assert b.query(Budget).filter_by(category="b-only").count() == 1
    assert report.overwrites["budgets"][0]["key"]["category"] == "groceries"


# ---------------------------------------------------------------------------
# Rule change reports carried in the snapshot
# ---------------------------------------------------------------------------


def test_rule_change_reports_merged_without_duplicates(db_a, db_b):
    (a, a_path), (b, b_path) = db_a, db_b
    report = RuleChangeReport(
        action="create",
        rule_uuid="00000000-0000-0000-0000-000000000009",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
        rule_after={"uuid": "00000000-0000-0000-0000-000000000009"},
        summary={"changed": 1},
    )
    report.items.append(RuleChangeItem(transaction_id="t1", old_category=None,
                                       new_category="groceries"))
    a.add(report)
    a.commit()
    snap = _export_bytes(a, a_path.parent)

    r1 = import_snapshot(b, snap, b_path)
    assert r1.counts["rule_change_reports"]["inserted"] == 1
    imported = b.query(RuleChangeReport).filter_by(action="create").one()
    assert imported.items[0].new_category == "groceries"

    # Re-import: same report matched, not duplicated.
    r2 = import_snapshot(b, snap, b_path)
    assert r2.counts["rule_change_reports"]["unchanged"] == 1
    assert b.query(RuleChangeReport).filter_by(action="create").count() == 1


# ---------------------------------------------------------------------------
# Rules are NOT reapplied after import — snapshot state is authoritative
# ---------------------------------------------------------------------------


def test_import_does_not_reapply_rules(db_a, db_b):
    (a, a_path), (b, b_path) = db_a, db_b
    a.add(make_txn("t1", description="albert heijn amsterdam", category="incoming-cat"))
    a.commit()
    # Local rule on B that would recategorize the incoming transaction if reapplied.
    b.add(make_rule("00000000-0000-0000-0000-00000000cafe",
                    match_value="albert heijn", category="local-rule-cat"))
    b.commit()
    snap = _export_bytes(a, a_path.parent)

    import_snapshot(b, snap, b_path)
    txn = b.get(Transaction, "t1")
    assert txn.category == "incoming-cat"  # NOT "local-rule-cat"


# ---------------------------------------------------------------------------
# Backup + transactionality
# ---------------------------------------------------------------------------


def test_backup_created_before_import(db_a, db_b):
    (a, a_path), (b, b_path) = db_a, db_b
    b.add(make_txn("pre-existing"))
    b.commit()
    pre_bytes = b_path.read_bytes()
    a.add(make_txn("t1"))
    a.commit()
    snap = _export_bytes(a, a_path.parent)

    import_snapshot(b, snap, b_path)
    backups = list(b_path.parent.glob("*.backup-*.db"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == pre_bytes


def test_failed_import_leaves_db_unchanged(db_a, db_b, monkeypatch):
    (a, a_path), (b, b_path) = db_a, db_b
    b.add(make_txn("t1", manual_category="local"))
    b.add(make_budget())
    b.commit()
    a.add(make_txn("t1", manual_category="incoming"))
    a.add(make_txn("t2"))
    a.add(make_rule())
    a.commit()
    snap = _export_bytes(a, a_path.parent)

    def boom():
        raise RuntimeError("injected failure")

    monkeypatch.setattr(snap_mod, "_pre_commit_hook", boom)
    with pytest.raises(RuntimeError, match="injected failure"):
        import_snapshot(b, snap, b_path)

    b.expire_all()
    assert b.get(Transaction, "t1").manual_category == "local"
    assert b.get(Transaction, "t2") is None
    assert b.query(CategorizationRule).count() == 0
    assert b.query(SnapshotImport).count() == 0
    assert b.query(RuleChangeReport).count() == 0


# ---------------------------------------------------------------------------
# Import report persistence
# ---------------------------------------------------------------------------


def test_import_persists_snapshot_import_and_change_report(db_a, db_b):
    (a, a_path), (b, b_path) = db_a, db_b
    a.add(make_txn("t1", category="dining"))
    b.add(make_txn("t1", category="groceries"))
    a.commit()
    b.commit()
    snap = _export_bytes(a, a_path.parent)

    result = import_snapshot(b, snap, b_path)
    stored = b.query(SnapshotImport).one()
    assert stored.id == result.id
    assert stored.schema_version == SCHEMA_VERSION
    assert stored.source_machine_id == snap["header"]["machine_id"]
    assert stored.counts["transactions"]["updated"] == 1

    # A RuleChangeReport with action="import" carries the per-txn category diff.
    change = b.query(RuleChangeReport).filter_by(action="import").one()
    (item,) = change.items
    assert item.transaction_id == "t1"
    assert item.old_category == "groceries"
    assert item.new_category == "dining"


# ---------------------------------------------------------------------------
# Full round trip: export A → import into fresh B reproduces effective data
# ---------------------------------------------------------------------------


def test_round_trip_reproduces_effective_data(db_a, db_b):
    (a, a_path), (b, b_path) = db_a, db_b
    rule = make_rule()
    rule.conditions.append(
        RuleCondition(field_target="name", match_pattern="contains",
                      match_value="ah", operator="AND", sort_order=0)
    )
    a.add(rule)
    a.flush()
    a.add(make_txn("t1", category="groceries", tags="auto",
                   categorization_source=str(rule.id),
                   description_structured='{"name": "ah utrecht"}'))
    a.add(make_txn("t2", manual_category="dining", manual_tags="friends",
                   categorization_source="manual"))
    a.add(make_budget())
    a.commit()
    rcr = RuleChangeReport(action="create", rule_uuid=rule.uuid,
                           rule_after={"uuid": rule.uuid}, summary={"changed": 1})
    rcr.items.append(RuleChangeItem(transaction_id="t1", new_category="groceries"))
    a.add(rcr)
    a.commit()

    snap = _export_bytes(a, a_path.parent)
    import_snapshot(b, snap, b_path)

    exported_again = build_snapshot(b, machine_id="check")
    original = build_snapshot(a, machine_id="check")
    assert exported_again["transactions"] == original["transactions"]
    assert exported_again["budgets"] == original["budgets"]
    # Rules compare on everything except the machine-local integer id.
    strip = lambda rules: [{k: v for k, v in r.items() if k != "id"} for r in rules]  # noqa: E731
    assert strip(exported_again["rules"]) == strip(original["rules"])
    # B additionally carries the audit report of the import itself; the carried
    # reports (everything else) must match.
    reports_strip = lambda reps: [  # noqa: E731
        {k: v for k, v in r.items() if k != "rule_id"}
        for r in reps
        if r["action"] != "import"
    ]
    assert reports_strip(exported_again["rule_change_reports"]) == reports_strip(
        original["rule_change_reports"]
    )


# ---------------------------------------------------------------------------
# The end-to-end reference across a snapshot
#
# The column feeds the duplicate check. A snapshot from an app before the column
# holds no such key, so the import must derive the value. Without this the
# reference check would do nothing on the machine that received the snapshot.
# See openspec/changes/unify-sepa-description-and-reference-dedup, tasks 5.5
# to 5.7.
# ---------------------------------------------------------------------------

_SEPA_STRUCTURED = (
    '{"format": "sepa", "transaction_type": "SEPA Direct Debit", '
    '"name": "LEBARA", "end_to_end_reference": "KFF5Q4D85TQK39G6"}'
)
_SEPA_TAGGED_DESCRIPTION = (
    "/TRTP/SEPA INCASSO ALGEMEEN DOORLOPEND/CSID/VP20XNL847867841319 "
    "/NAME/LEBARA/MARF/B0OXIVC5T2O3ZJ58/REMI/LEBARA NL-039442543-277 "
    "/IBAN/NL65ADYB0257164544/BIC/ADYBNL2A/EREF/KFF5Q4D85TQK39G6"
)


def test_snapshot_carries_the_reference(db_a, db_b):
    """Task 5.5: the field travels when the snapshot holds it."""
    (a, a_path), (b, b_path) = db_a, db_b
    a.add(
        make_txn(
            "t1",
            description_structured=_SEPA_STRUCTURED,
            end_to_end_reference="KFF5Q4D85TQK39G6",
        )
    )
    a.commit()
    snap = _export_bytes(a, a_path.parent)

    import_snapshot(b, snap, b_path)

    assert b.get(Transaction, "t1").end_to_end_reference == "KFF5Q4D85TQK39G6"


def test_snapshot_without_the_field_derives_the_reference(db_a, db_b):
    """Task 5.5: a snapshot from an app before the column still fills it."""
    (a, a_path), (b, b_path) = db_a, db_b
    a.add(make_txn("t1", description_structured=_SEPA_STRUCTURED))
    a.commit()
    snap = _export_bytes(a, a_path.parent)

    # Model the older snapshot: remove the key from each transaction.
    for data in snap["transactions"]:
        data.pop("end_to_end_reference", None)

    import_snapshot(b, snap, b_path)

    assert b.get(Transaction, "t1").end_to_end_reference == "KFF5Q4D85TQK39G6"


def test_a_merge_reaches_a_second_machine(db_a, db_b):
    """The flag and the survivor id both travel in a snapshot.

    Covers the scenario "A merge reaches a second machine" of the
    manual-transactions delta. Without this the second machine would show the
    payment twice.
    """
    (a, a_path), (b, b_path) = db_a, db_b
    a.add(
        make_txn(
            "aaa-survivor",
            description_structured=_SEPA_STRUCTURED,
            end_to_end_reference="KFF5Q4D85TQK39G6",
        )
    )
    a.add(
        make_txn(
            "zzz-folded",
            description_structured=_SEPA_STRUCTURED,
            end_to_end_reference="KFF5Q4D85TQK39G6",
        )
    )
    a.commit()

    from abn_combined.core.merge import merge_duplicates

    result = merge_duplicates(a)
    assert len(result.groups) == 1

    snap = _export_bytes(a, a_path.parent)
    import_snapshot(b, snap, b_path)

    survivor = b.get(Transaction, "aaa-survivor")
    folded = b.get(Transaction, "zzz-folded")
    assert survivor.merged_into is None
    assert survivor.deleted_at is None
    assert folded.merged_into == "aaa-survivor"
    assert folded.deleted_at is not None


def test_a_merged_row_stays_out_of_each_total_after_a_sync(db_a, db_b):
    """The second machine hides the folded row, so each total holds it once."""
    from abn_combined.core.filters import live_only
    from abn_combined.core.merge import merge_duplicates

    (a, a_path), (b, b_path) = db_a, db_b
    for txn_id in ("aaa-survivor", "zzz-folded"):
        a.add(
            make_txn(
                txn_id,
                description_structured=_SEPA_STRUCTURED,
                end_to_end_reference="KFF5Q4D85TQK39G6",
            )
        )
    a.commit()
    merge_duplicates(a)
    import_snapshot(b, _export_bytes(a, a_path.parent), b_path)

    live = live_only(b.query(Transaction)).all()

    assert [row.id for row in live] == ["aaa-survivor"]


def test_an_import_matches_a_payment_that_a_snapshot_supplied(db_a, db_b):
    """Task 5.6: a later statement import does not write a second row."""
    from abn_combined.core.dedup import check_duplicates
    from abn_combined.parsers.description import parse_transaction_description

    (a, a_path), (b, b_path) = db_a, db_b
    a.add(make_txn("t1", description_structured=_SEPA_STRUCTURED))
    a.commit()
    snap = _export_bytes(a, a_path.parent)
    for data in snap["transactions"]:
        data.pop("end_to_end_reference", None)
    import_snapshot(b, snap, b_path)

    # The same payment arrives again, now from a statement of that account. Its
    # id differs, because the raw description of the statement differs.
    structured = parse_transaction_description(_SEPA_TAGGED_DESCRIPTION)
    incoming = {
        "accountNumber": "NL01TEST0123456789",
        "transactiondate": date(2026, 1, 15),
        "amount": Decimal("-42.50"),
        "description": _SEPA_TAGGED_DESCRIPTION,
        "currency": "EUR",
        "description_structured": json.dumps(structured, ensure_ascii=False),
    }

    new, dup = check_duplicates(b, [incoming])

    assert new == []
    assert len(dup) == 1


def test_the_snapshot_import_writes_a_row_with_a_known_reference(db_a, db_b):
    """Task 5.7: the snapshot import stays the only path that may replace a row.

    The reference check belongs to the statement import. It must not block a
    snapshot row whose reference matches a stored row with another id.
    """
    (a, a_path), (b, b_path) = db_a, db_b
    a.add(
        make_txn(
            "from_machine_a",
            description_structured=_SEPA_STRUCTURED,
            end_to_end_reference="KFF5Q4D85TQK39G6",
        )
    )
    a.commit()
    snap = _export_bytes(a, a_path.parent)

    # The receiving machine already holds the same payment under another id.
    b.add(
        make_txn(
            "local_other_id",
            description_structured=_SEPA_STRUCTURED,
            end_to_end_reference="KFF5Q4D85TQK39G6",
        )
    )
    b.commit()

    report = import_snapshot(b, snap, b_path)

    assert report.counts["transactions"]["inserted"] == 1
    assert b.get(Transaction, "from_machine_a") is not None
    assert b.get(Transaction, "local_other_id") is not None


# ---------------------------------------------------------------------------
# Several budgets for one category (repeating-budgets-with-override)
# ---------------------------------------------------------------------------


def test_two_budgets_for_one_category_arrive(db_a, db_b):
    (a, a_path), (b, b_path) = db_a, db_b
    a.add(make_budget(start_date=date(2026, 7, 1), end_date=date(2026, 10, 31),
                      amount=Decimal("100.00")))
    a.add(make_budget(start_date=date(2026, 11, 1), amount=Decimal("150.00")))
    b.add(make_budget(start_date=date(2026, 7, 1), end_date=date(2026, 10, 31),
                      amount=Decimal("90.00")))
    a.commit()
    b.commit()

    report = import_snapshot(b, _export_bytes(a, a_path.parent), b_path)
    b.expire_all()
    assert report.counts["budgets"] == {"inserted": 1, "updated": 1, "unchanged": 0}
    rows = [(r.start_date, r.end_date, r.amount)
            for r in b.query(Budget).order_by(Budget.start_date)]
    assert rows == [(date(2026, 7, 1), date(2026, 10, 31), Decimal("100.00")),
                    (date(2026, 11, 1), None, Decimal("150.00"))]


def test_incoming_budget_replaces_an_overlapping_local_budget(db_a, db_b):
    (a, a_path), (b, b_path) = db_a, db_b
    a.add(make_budget(start_date=date(2026, 8, 1), amount=Decimal("150.00")))
    b.add(make_budget(start_date=date(2026, 7, 1), amount=Decimal("100.00")))
    b.add(make_budget(category="other", start_date=date(2026, 7, 1)))
    a.commit()
    b.commit()

    report = import_snapshot(b, _export_bytes(a, a_path.parent), b_path)
    b.expire_all()
    groceries = b.query(Budget).filter_by(category="groceries").all()
    assert [(g.start_date, g.amount) for g in groceries] == [(date(2026, 8, 1), Decimal("150.00"))]
    assert b.query(Budget).filter_by(category="other").count() == 1
    [deleted] = report.overwrites["budgets"]
    assert deleted["key"] == {"category": "groceries", "period": "month",
                              "start_date": "2026-07-01"}
    assert "deleted" in deleted["fields"]
