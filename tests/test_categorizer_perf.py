"""Performance benchmark for rule reapplication (NFR3: < 10s at 50k rows)."""

from __future__ import annotations

import time
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from abn_combined.core.categorizer import record_rule_change
from abn_combined.core.models import Base, CategorizationRule, RuleChangeItem, Transaction


@pytest.mark.slow
def test_reapply_50k_under_10s(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'perf.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for i, kw in enumerate(("supermarkt", "netflix", "spotify", "salary", "rent")):
            session.add(
                CategorizationRule(
                    priority=10 + i,
                    rule_type="keyword",
                    match_pattern="contains",
                    field_target="description",
                    match_value=kw,
                    category=kw,
                )
            )
        descriptions = ["AH SUPERMARKT", "NETFLIX INTL", "random purchase", "SPOTIFY", "SALARY"]
        session.bulk_save_objects(
            [
                Transaction(
                    id=f"acct_{i}",
                    accountNumber="ACC",
                    transactiondate=date(2024, 1, 1),
                    amount=-1.0,
                    currency="EUR",
                    description=descriptions[i % len(descriptions)],
                )
                for i in range(50_000)
            ]
        )
        session.commit()

        start = time.perf_counter()
        report = record_rule_change(session, action="recategorize")
        elapsed = time.perf_counter() - start

        assert elapsed < 10.0, f"reapply took {elapsed:.2f}s"
        # 4 of every 5 descriptions match a rule.
        assert session.query(RuleChangeItem).filter_by(report_id=report.id).count() > 30_000
