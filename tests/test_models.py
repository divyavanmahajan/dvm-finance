"""Model round-trip and constraint tests."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from abn_combined.core.models import (
    Base,
    Budget,
    CategorizationRule,
    DownloadState,
    RuleChangeItem,
    RuleChangeReport,
    RuleCondition,
    SnapshotImport,
    Transaction,
)


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_transaction_round_trip(session):
    txn = Transaction(
        id="acct_2024-01-01_-5.75_abc",
        accountNumber="869623141",
        transactiondate=date(2024, 1, 1),
        amount=-5.75,
        description="BEA test",
        currency="EUR",
        source_file="x.STA",
        source_line=7,
        transaction_hash="deadbeef",
    )
    session.add(txn)
    session.commit()
    got = session.get(Transaction, "acct_2024-01-01_-5.75_abc")
    assert got.accountNumber == "869623141"
    assert got.transactiondate == date(2024, 1, 1)
    assert float(got.amount) == -5.75
    assert got.source_line == 7


def test_rule_uuid_auto_generated(session):
    rule = CategorizationRule(
        rule_type="keyword",
        match_pattern="contains",
        field_target="description",
        match_value="supermarkt",
        category="groceries",
    )
    session.add(rule)
    session.commit()
    assert rule.uuid is not None
    assert len(rule.uuid) == 36
    # A second rule gets a distinct uuid.
    rule2 = CategorizationRule(
        rule_type="keyword",
        match_pattern="contains",
        field_target="description",
        match_value="restaurant",
        category="dining",
    )
    session.add(rule2)
    session.commit()
    assert rule2.uuid != rule.uuid


def test_rule_defaults(session):
    rule = CategorizationRule(
        rule_type="keyword",
        match_pattern="contains",
        field_target="description",
        match_value="x",
        category="c",
    )
    session.add(rule)
    session.commit()
    assert rule.priority == 100
    assert rule.is_active is True


def test_rule_condition_cascade_delete(session):
    rule = CategorizationRule(
        rule_type="keyword",
        match_pattern="contains",
        field_target="description",
        match_value="x",
        category="c",
    )
    rule.conditions.append(
        RuleCondition(field_target="description", match_pattern="contains", match_value="y")
    )
    rule.conditions.append(
        RuleCondition(
            field_target="name", match_pattern="exact", match_value="z", operator="OR", sort_order=1
        )
    )
    session.add(rule)
    session.commit()
    assert session.scalars(select(RuleCondition)).all().__len__() == 2

    session.delete(rule)
    session.commit()
    assert session.scalars(select(RuleCondition)).all() == []


def test_change_report_items_cascade(session):
    report = RuleChangeReport(action="update", rule_id=1, summary={"changed": 2})
    report.items.append(
        RuleChangeItem(transaction_id="t1", old_category="a", new_category="b")
    )
    report.items.append(
        RuleChangeItem(transaction_id="t2", old_category=None, new_category="b")
    )
    session.add(report)
    session.commit()
    assert report.summary == {"changed": 2}
    assert len(session.scalars(select(RuleChangeItem)).all()) == 2

    session.delete(report)
    session.commit()
    assert session.scalars(select(RuleChangeItem)).all() == []


def test_budget_round_trip(session):
    b = Budget(category="groceries", amount=250, period="month")
    session.add(b)
    session.commit()
    got = session.scalars(select(Budget)).one()
    assert got.category == "groceries"
    assert float(got.amount) == 250


def test_download_state_round_trip(session):
    ds = DownloadState(
        source="abnamro",
        account="869623141",
        last_success_at=datetime(2026, 1, 1, 12, 0),
        last_range_end=date(2026, 1, 1),
    )
    session.add(ds)
    session.commit()
    got = session.scalars(select(DownloadState)).one()
    assert got.source == "abnamro"


def test_snapshot_import_round_trip(session):
    si = SnapshotImport(
        source_machine_id="mac-123",
        schema_version=1,
        counts={"transactions": {"inserted": 5}},
        overwrites={"rules": ["uuid-1"]},
    )
    session.add(si)
    session.commit()
    got = session.scalars(select(SnapshotImport)).one()
    assert got.counts["transactions"]["inserted"] == 5
    assert got.overwrites["rules"] == ["uuid-1"]
