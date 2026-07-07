"""SQLAlchemy 2.x models (ported from abn-analyst, plus audit/sharing tables).

Legacy column names (``accountNumber``, ``transactiondate``, ...) are preserved so
the legacy migration and snapshot format stay simple.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid4_str() -> str:
    return str(uuid.uuid4())


class Transaction(Base):
    """Transaction model matching the legacy XLS structure."""

    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    accountNumber: Mapped[str] = mapped_column(String, nullable=False, index=True)
    mutationcode: Mapped[str | None] = mapped_column(String)
    transactiondate: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valuedate: Mapped[date | None] = mapped_column(Date)
    startsaldo: Mapped[float | None] = mapped_column(Numeric(15, 2))
    endsaldo: Mapped[float | None] = mapped_column(Numeric(15, 2))
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String)
    description_structured: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String, index=True)
    manual_category: Mapped[str | None] = mapped_column(String, index=True)
    tags: Mapped[str | None] = mapped_column(String)
    manual_tags: Mapped[str | None] = mapped_column(String)
    categorization_source: Mapped[str | None] = mapped_column(String)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    source_file: Mapped[str | None] = mapped_column(String, nullable=True)
    source_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transaction_type_code: Mapped[str | None] = mapped_column(String, nullable=True)
    transaction_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    transaction_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    __table_args__ = (Index("idx_account_date", "accountNumber", "transactiondate"),)


class CategorizationRule(Base):
    """User-editable categorization rule."""

    __tablename__ = "categorization_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, default=_uuid4_str, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    match_pattern: Mapped[str] = mapped_column(String(50), nullable=False)
    field_target: Mapped[str | None] = mapped_column(String(50))
    match_value: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    tags: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    # Context filters — all optional (NULL = no restriction)
    filter_account: Mapped[str | None] = mapped_column(String, nullable=True)
    filter_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    filter_date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    filter_date_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    conditions: Mapped[list[RuleCondition]] = relationship(
        "RuleCondition",
        cascade="all, delete-orphan",
        order_by="RuleCondition.sort_order",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_rules_priority_active", "priority", "is_active"),
        Index("idx_rules_type", "rule_type"),
    )


class RuleCondition(Base):
    """Additional condition for a categorization rule (AND/OR with the primary)."""

    __tablename__ = "rule_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("categorization_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_target: Mapped[str] = mapped_column(String(50), nullable=False)
    match_pattern: Mapped[str] = mapped_column(String(50), nullable=False)
    match_value: Mapped[str] = mapped_column(String(500), nullable=False)
    operator: Mapped[str] = mapped_column(String(3), nullable=False, default="AND")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Budget(Base):
    """Budget model for tracking spending limits per category."""

    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    period: Mapped[str] = mapped_column(String(10), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[date | None] = mapped_column(Date, default=date.today)
    updated_at: Mapped[date | None] = mapped_column(
        Date, default=date.today, onupdate=date.today
    )

    __table_args__ = (
        Index("idx_budgets_category", "category"),
        Index("idx_budgets_period", "period"),
        Index("idx_budgets_category_period", "category", "period", unique=True),
    )


# ---------------------------------------------------------------------------
# New tables vs abn-analyst: audit + sharing
# ---------------------------------------------------------------------------

RULE_CHANGE_ACTIONS = ("create", "update", "delete", "toggle", "recategorize", "import")


class RuleChangeReport(Base):
    """Audit record for a rule mutation or a recategorization/import run."""

    __tablename__ = "rule_change_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), index=True
    )
    rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    rule_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rule_after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    items: Mapped[list[RuleChangeItem]] = relationship(
        "RuleChangeItem",
        cascade="all, delete-orphan",
        back_populates="report",
        lazy="selectin",
    )


class RuleChangeItem(Base):
    """Per-transaction before/after diff belonging to a RuleChangeReport."""

    __tablename__ = "rule_change_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("rule_change_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    old_category: Mapped[str | None] = mapped_column(String, nullable=True)
    new_category: Mapped[str | None] = mapped_column(String, nullable=True)
    old_tags: Mapped[str | None] = mapped_column(String, nullable=True)
    new_tags: Mapped[str | None] = mapped_column(String, nullable=True)

    report: Mapped[RuleChangeReport] = relationship(
        "RuleChangeReport", back_populates="items"
    )


class DownloadState(Base):
    """Last successful download bookmark per source/account."""

    __tablename__ = "download_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    account: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_range_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        Index("idx_download_state_source_account", "source", "account", unique=True),
    )


class SnapshotImport(Base):
    """Report for a snapshot import (incoming-wins merge)."""

    __tablename__ = "snapshot_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), index=True
    )
    source_machine_id: Mapped[str | None] = mapped_column(String, nullable=True)
    schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    overwrites: Mapped[dict | None] = mapped_column(JSON, nullable=True)
