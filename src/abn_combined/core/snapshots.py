"""Snapshot export/import — the FR9 sharing mechanism.

A snapshot is a single gzipped JSON file with a versioned header and the full
dataset: transactions (every column, including manual fields and
``categorization_source``), rules keyed by ``uuid`` (with conditions), budgets,
and rule-change reports. Import merges with **incoming-wins** semantics:

- new rows are inserted;
- on identity collision the snapshot value overwrites local — including manual
  categorizations and rule definitions. This is the *only* path allowed to
  overwrite manual edits (Golden Principle 2), and only via explicit user
  action with a stored report;
- local rows absent from the snapshot are never deleted.

Identity is deterministic (Golden Principle 10): transactions by their
deterministic id, rules by ``uuid``, budgets by (category, period, start_date).

The whole merge runs in ONE database transaction, after the sqlite DB file has
been backed up to a timestamped copy in the data dir. Rules are deliberately
NOT reapplied after import: the snapshot carries the final categorization
state, which is authoritative.
"""

from __future__ import annotations

import gzip
import json
import shutil
import uuid as uuid_mod
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..logging_config import get_logger
from .categorizer import rule_snapshot
from .models import (
    Budget,
    CategorizationRule,
    ExportState,
    RuleChangeItem,
    RuleChangeReport,
    RuleCondition,
    SnapshotImport,
    Transaction,
)

logger = get_logger(__name__)

SCHEMA_VERSION = 1
SNAPSHOT_SUFFIX = ".json.gz"
_ENTITY_KEYS = ("transactions", "rules", "budgets", "rule_change_reports")


class SnapshotError(ValueError):
    """A snapshot file was rejected (corrupt, malformed, or wrong schema version)."""


# ---------------------------------------------------------------------------
# Machine id: a uuid persisted per data dir, so exports identify their source.
# ---------------------------------------------------------------------------


def get_machine_id(data_dir: Path) -> str:
    marker = data_dir / "machine_id"
    if marker.exists():
        value = marker.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = str(uuid_mod.uuid4())
    data_dir.mkdir(parents=True, exist_ok=True)
    marker.write_text(value, encoding="utf-8")
    return value


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

_TXN_COLUMNS = [c.name for c in Transaction.__table__.columns]
_TXN_DATE_COLUMNS = {"transactiondate", "valuedate"}
_TXN_DATETIME_COLUMNS = {"updated_at"}
_TXN_NUMERIC_COLUMNS = {"startsaldo", "endsaldo", "amount"}


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _txn_dict(txn: Transaction) -> dict[str, Any]:
    return {col: _json_safe(getattr(txn, col)) for col in _TXN_COLUMNS}


def _budget_key(data: dict[str, Any]) -> tuple:
    return (data.get("category"), data.get("period"), data.get("start_date"))


def _budget_dict(budget: Budget) -> dict[str, Any]:
    return {
        "category": budget.category,
        "amount": _json_safe(budget.amount),
        "period": budget.period,
        "start_date": _json_safe(budget.start_date),
        "end_date": _json_safe(budget.end_date),
        "notes": budget.notes,
    }


def _report_dict(report: RuleChangeReport) -> dict[str, Any]:
    return {
        "created_at": _json_safe(report.created_at),
        "rule_id": report.rule_id,
        "rule_uuid": report.rule_uuid,
        "action": report.action,
        "rule_before": report.rule_before,
        "rule_after": report.rule_after,
        "summary": report.summary,
        "items": [
            {
                "transaction_id": i.transaction_id,
                "old_category": i.old_category,
                "new_category": i.new_category,
                "old_tags": i.old_tags,
                "new_tags": i.new_tags,
            }
            for i in report.items
        ],
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def build_snapshot(
    db: Session, machine_id: str, since: datetime | None = None
) -> dict[str, Any]:
    """Serialise the dataset into the (JSON-safe) snapshot payload.

    When ``since`` is provided this is a **delta** snapshot: the ``transactions``
    array is limited to rows whose ``updated_at >= since`` (rows never touched
    since this column was added — ``updated_at IS NULL`` — are excluded), and
    the header carries ``"delta": true`` and ``"since": "<iso8601>"`` so the
    file is self-describing. The format is otherwise identical to a full
    snapshot (same header/entity shape), and rules/budgets/reports are still
    exported in full — the import path is unchanged (incoming-wins per present
    transaction row, never deleting absent local rows), so a delta is just "a
    snapshot with fewer transactions".
    """
    header: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "machine_id": machine_id,
    }
    txn_query = db.query(Transaction)
    if since is not None:
        header["delta"] = True
        header["since"] = since.isoformat(timespec="seconds")
        txn_query = txn_query.filter(Transaction.updated_at.isnot(None)).filter(
            Transaction.updated_at >= since
        )
    return {
        "header": header,
        "transactions": [
            _txn_dict(t) for t in txn_query.order_by(Transaction.id.asc()).all()
        ],
        "rules": [
            rule_snapshot(r)
            for r in db.query(CategorizationRule)
            .order_by(CategorizationRule.uuid.asc())
            .all()
        ],
        "budgets": [
            _budget_dict(b) for b in db.query(Budget).order_by(Budget.id.asc()).all()
        ],
        "rule_change_reports": [
            _report_dict(r)
            for r in db.query(RuleChangeReport)
            .order_by(RuleChangeReport.created_at.asc(), RuleChangeReport.id.asc())
            .all()
        ],
    }


def get_export_state(db: Session) -> ExportState:
    """Return the single ``export_state`` row, creating it (id=1) if absent."""
    state = db.query(ExportState).order_by(ExportState.id.asc()).first()
    if state is None:
        state = ExportState()
        db.add(state)
        db.flush()
    return state


def get_last_delta_export_at(db: Session) -> datetime | None:
    """The ``since`` boundary the delta-export form defaults to, or ``None``."""
    state = db.query(ExportState).order_by(ExportState.id.asc()).first()
    return state.last_delta_export_at if state is not None else None


def export_snapshot(
    db: Session, data_dir: Path, since: datetime | None = None
) -> Path:
    """Write a gzipped snapshot to ``<data_dir>/snapshots/`` and return its path.

    When ``since`` is given, exports a **delta** snapshot (see
    :func:`build_snapshot`) and advances the ``export_state`` marker to the
    export time, so the next delta defaults to "changes since this one".
    """
    snapshots_dir = data_dir / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    export_started_at = datetime.now()
    payload = build_snapshot(db, machine_id=get_machine_id(data_dir), since=since)
    if since is not None:
        state = get_export_state(db)
        state.last_delta_export_at = export_started_at
        db.commit()
    prefix = "delta" if since is not None else "snapshot"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = snapshots_dir / f"{prefix}-{stamp}{SNAPSHOT_SUFFIX}"
    # Avoid clobbering a snapshot exported within the same second.
    n = 1
    while path.exists():
        path = snapshots_dir / f"{prefix}-{stamp}-{n}{SNAPSHOT_SUFFIX}"
        n += 1
    blob = gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    path.write_bytes(blob)
    logger.info("snapshot_exported", path=str(path), size=len(blob))
    return path


def list_exports(data_dir: Path) -> list[dict[str, Any]]:
    """Past exports in ``<data_dir>/snapshots/``, newest first: name/modified/size."""
    snapshots_dir = data_dir / "snapshots"
    if not snapshots_dir.is_dir():
        return []
    entries = [
        {
            "name": p.name,
            "modified": datetime.fromtimestamp(p.stat().st_mtime),
            "size": p.stat().st_size,
        }
        for p in snapshots_dir.glob(f"*{SNAPSHOT_SUFFIX}")
    ]
    entries.sort(key=lambda e: e["modified"], reverse=True)
    return entries


# ---------------------------------------------------------------------------
# Reading + validation
# ---------------------------------------------------------------------------


def read_snapshot(blob: bytes) -> dict[str, Any]:
    """Decompress, parse and validate a snapshot file.

    Raises :class:`SnapshotError` with a clear message on corrupt gzip, corrupt
    JSON, a malformed payload, or a schema-version mismatch.
    """
    try:
        raw = gzip.decompress(blob)
    except (OSError, EOFError) as exc:
        raise SnapshotError(f"Not a valid snapshot file (corrupt gzip): {exc}") from exc
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SnapshotError(f"Not a valid snapshot file (corrupt JSON): {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("header"), dict):
        raise SnapshotError("Not a valid snapshot file (missing header).")
    version = payload["header"].get("schema_version")
    if version != SCHEMA_VERSION:
        raise SnapshotError(
            f"Schema version mismatch: snapshot has version {version!r}, "
            f"this app supports version {SCHEMA_VERSION}."
        )
    for key in _ENTITY_KEYS:
        if not isinstance(payload.get(key), list):
            raise SnapshotError(f"Not a valid snapshot file (missing '{key}').")
    return payload


# ---------------------------------------------------------------------------
# Import: backup, then one incoming-wins merge transaction
# ---------------------------------------------------------------------------


def _backup_db(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db_path.parent / f"{db_path.stem}.backup-{stamp}{db_path.suffix}"
    n = 1
    while backup.exists():
        backup = db_path.parent / f"{db_path.stem}.backup-{stamp}-{n}{db_path.suffix}"
        n += 1
    shutil.copy2(db_path, backup)
    logger.info("db_backed_up", backup=str(backup))
    return backup


def _pre_commit_hook() -> None:
    """Test seam: monkeypatched to inject a failure just before commit."""


def _parse_date(value: Any) -> date | None:
    return date.fromisoformat(value) if value else None


def _parse_datetime(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _diff(local: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    return {
        key: {"local": local.get(key), "incoming": incoming.get(key)}
        for key in incoming
        if local.get(key) != incoming.get(key)
    }


def _effective(category: str | None, manual: str | None) -> str | None:
    return manual or category


class _Counter:
    def __init__(self) -> None:
        self.inserted = 0
        self.updated = 0
        self.unchanged = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
        }


def _merge_rules(
    db: Session, incoming_rules: list[dict[str, Any]]
) -> tuple[_Counter, list[dict], dict[str, int]]:
    """Incoming-wins merge of rules by uuid. Returns (counts, overwrites, id map).

    The id map translates *incoming* machine-local rule ids to local ids, so
    transaction ``categorization_source`` values can be remapped.
    """
    counter = _Counter()
    overwrites: list[dict] = []
    id_map: dict[str, int] = {}

    for data in incoming_rules:
        incoming_id = data.get("id")
        local = (
            db.query(CategorizationRule).filter_by(uuid=data["uuid"]).one_or_none()
        )
        incoming_cmp = {k: v for k, v in data.items() if k != "id"}
        if local is not None:
            local_snap = rule_snapshot(local) or {}
            local_cmp = {k: v for k, v in local_snap.items() if k != "id"}
            if local_cmp == incoming_cmp:
                counter.unchanged += 1
            else:
                overwrites.append(
                    {"uuid": data["uuid"], "fields": _diff(local_cmp, incoming_cmp)}
                )
                _apply_rule_data(local, data)
                counter.updated += 1
        else:
            local = CategorizationRule(uuid=data["uuid"])
            _apply_rule_data(local, data)
            db.add(local)
            counter.inserted += 1
        db.flush()  # assign local.id for the id map
        if incoming_id is not None:
            id_map[str(incoming_id)] = local.id
    return counter, overwrites, id_map


def _apply_rule_data(rule: CategorizationRule, data: dict[str, Any]) -> None:
    rule.priority = data.get("priority", 100)
    rule.rule_type = data["rule_type"]
    rule.match_pattern = data["match_pattern"]
    rule.field_target = data.get("field_target")
    rule.match_value = data["match_value"]
    rule.category = data.get("category")
    rule.tags = data.get("tags")
    rule.is_active = data.get("is_active", True)
    rule.is_tag_only = data.get("is_tag_only", False)
    rule.notes = data.get("notes")
    rule.filter_account = data.get("filter_account")
    rule.filter_currency = data.get("filter_currency")
    rule.filter_date_from = _parse_date(data.get("filter_date_from"))
    rule.filter_date_to = _parse_date(data.get("filter_date_to"))
    rule.conditions.clear()  # incoming wins: conditions replaced wholesale
    for cond in data.get("conditions") or []:
        rule.conditions.append(
            RuleCondition(
                field_target=cond["field_target"],
                match_pattern=cond["match_pattern"],
                match_value=cond["match_value"],
                operator=cond.get("operator", "AND"),
                sort_order=cond.get("sort_order", 0),
            )
        )


def _txn_from_data(data: dict[str, Any]) -> dict[str, Any]:
    """Convert a serialized transaction dict back to ORM-typed values."""
    values: dict[str, Any] = {}
    for col in _TXN_COLUMNS:
        value = data.get(col)
        if col in _TXN_DATE_COLUMNS:
            value = _parse_date(value)
        elif col in _TXN_DATETIME_COLUMNS:
            value = _parse_datetime(value)
        elif col in _TXN_NUMERIC_COLUMNS and value is not None:
            value = Decimal(str(value))
        values[col] = value
    return values


def _merge_transactions(
    db: Session,
    incoming_txns: list[dict[str, Any]],
    rule_id_map: dict[str, int],
) -> tuple[_Counter, list[dict], list[RuleChangeItem]]:
    counter = _Counter()
    overwrites: list[dict] = []
    change_items: list[RuleChangeItem] = []

    for data in incoming_txns:
        data = dict(data)
        # categorization_source stores str(rule.id), which is machine-local;
        # remap incoming ids to the local id of the same rule (matched by uuid).
        source = data.get("categorization_source")
        if source in rule_id_map:
            data["categorization_source"] = str(rule_id_map[source])

        local = db.get(Transaction, data["id"])
        if local is None:
            db.add(Transaction(**_txn_from_data(data)))
            counter.inserted += 1
            continue

        local_dict = _txn_dict(local)
        if local_dict == data:
            counter.unchanged += 1
            continue

        # Incoming wins — including manual_category/manual_tags. This is the
        # only code path allowed to overwrite manual edits (Golden Principle 2),
        # and it always records what it overwrote.
        fields = _diff(local_dict, data)
        overwrites.append({"id": data["id"], "fields": fields})
        old_eff_cat = _effective(local_dict.get("category"),
                                 local_dict.get("manual_category"))
        old_eff_tags = _effective(local_dict.get("tags"), local_dict.get("manual_tags"))
        new_eff_cat = _effective(data.get("category"), data.get("manual_category"))
        new_eff_tags = _effective(data.get("tags"), data.get("manual_tags"))
        if (old_eff_cat, old_eff_tags) != (new_eff_cat, new_eff_tags):
            change_items.append(
                RuleChangeItem(
                    transaction_id=data["id"],
                    old_category=old_eff_cat,
                    new_category=new_eff_cat,
                    old_tags=old_eff_tags,
                    new_tags=new_eff_tags,
                )
            )
        for col, value in _txn_from_data(data).items():
            if col != "id":
                setattr(local, col, value)
        counter.updated += 1

    return counter, overwrites, change_items


def _merge_budgets(
    db: Session, incoming_budgets: list[dict[str, Any]]
) -> tuple[_Counter, list[dict]]:
    counter = _Counter()
    overwrites: list[dict] = []
    for data in incoming_budgets:
        key = _budget_key(data)
        local = (
            db.query(Budget)
            .filter(
                Budget.category == data["category"],
                Budget.period == data["period"],
                Budget.start_date == _parse_date(data.get("start_date")),
            )
            .one_or_none()
        )
        if local is None:
            # (category, period) is DB-unique; a row with the same pair but a
            # different start_date still collides — incoming wins on that row.
            local = (
                db.query(Budget)
                .filter(Budget.category == data["category"],
                        Budget.period == data["period"])
                .one_or_none()
            )
        if local is None:
            db.add(
                Budget(
                    category=data["category"],
                    amount=Decimal(str(data["amount"])),
                    period=data["period"],
                    start_date=_parse_date(data.get("start_date")),
                    end_date=_parse_date(data.get("end_date")),
                    notes=data.get("notes"),
                )
            )
            counter.inserted += 1
            continue
        local_dict = _budget_dict(local)
        if local_dict == data:
            counter.unchanged += 1
            continue
        overwrites.append(
            {
                "key": {"category": key[0], "period": key[1], "start_date": key[2]},
                "fields": _diff(local_dict, data),
            }
        )
        local.amount = Decimal(str(data["amount"]))
        local.start_date = _parse_date(data.get("start_date"))
        local.end_date = _parse_date(data.get("end_date"))
        local.notes = data.get("notes")
        counter.updated += 1
    return counter, overwrites


def _merge_reports(
    db: Session,
    incoming_reports: list[dict[str, Any]],
    rule_id_map: dict[str, int],
) -> _Counter:
    """Merge rule-change reports.

    Reports have no cross-machine uuid; (created_at, action, rule_uuid) is used
    as a stable-enough identity so re-importing a snapshot does not duplicate
    the audit trail. Existing local reports are never modified or deleted.
    """
    counter = _Counter()
    existing = {
        (
            r.created_at.isoformat() if r.created_at else None,
            r.action,
            r.rule_uuid,
        )
        for r in db.query(RuleChangeReport).all()
    }
    for data in incoming_reports:
        key = (data.get("created_at"), data.get("action"), data.get("rule_uuid"))
        if key in existing:
            counter.unchanged += 1
            continue
        incoming_rule_id = data.get("rule_id")
        report = RuleChangeReport(
            created_at=_parse_datetime(data.get("created_at")) or datetime.now(),
            rule_id=rule_id_map.get(str(incoming_rule_id))
            if incoming_rule_id is not None
            else None,
            rule_uuid=data.get("rule_uuid"),
            action=data.get("action") or "update",
            rule_before=data.get("rule_before"),
            rule_after=data.get("rule_after"),
            summary=data.get("summary"),
        )
        for item in data.get("items") or []:
            report.items.append(
                RuleChangeItem(
                    transaction_id=item["transaction_id"],
                    old_category=item.get("old_category"),
                    new_category=item.get("new_category"),
                    old_tags=item.get("old_tags"),
                    new_tags=item.get("new_tags"),
                )
            )
        db.add(report)
        existing.add(key)
        counter.inserted += 1
    return counter


def import_snapshot(db: Session, snapshot: dict[str, Any], db_path: Path) -> SnapshotImport:
    """Merge a validated snapshot payload into the local database.

    Backs the sqlite DB file up to a timestamped copy first, then runs the whole
    incoming-wins merge (plus the SnapshotImport row and the action="import"
    RuleChangeReport) in ONE transaction — any failure rolls everything back.

    Rules are deliberately NOT reapplied afterwards: the snapshot's
    categorization state (including ``categorization_source``) is authoritative.
    """
    header = snapshot["header"]
    if db_path.exists():
        _backup_db(db_path)

    try:
        rule_counts, rule_overwrites, rule_id_map = _merge_rules(db, snapshot["rules"])
        txn_counts, txn_overwrites, change_items = _merge_transactions(
            db, snapshot["transactions"], rule_id_map
        )
        budget_counts, budget_overwrites = _merge_budgets(db, snapshot["budgets"])
        report_counts = _merge_reports(db, snapshot["rule_change_reports"], rule_id_map)

        counts = {
            "transactions": txn_counts.as_dict(),
            "rules": rule_counts.as_dict(),
            "budgets": budget_counts.as_dict(),
            "rule_change_reports": report_counts.as_dict(),
        }
        overwrites = {
            "transactions": txn_overwrites,
            "rules": rule_overwrites,
            "budgets": budget_overwrites,
        }

        # Audit trail: an action="import" RuleChangeReport (renders in the rules
        # History list) carrying the per-transaction effective category/tag diff.
        # Built directly — NOT via record_rule_change, which would reapply rules.
        change_report = RuleChangeReport(
            action="import",
            summary={
                "changed": len(change_items),
                **{
                    f"{entity}_{kind}": n
                    for entity, entity_counts in counts.items()
                    for kind, n in entity_counts.items()
                    if n
                },
            },
        )
        change_report.items.extend(change_items)
        db.add(change_report)

        result = SnapshotImport(
            source_machine_id=header.get("machine_id"),
            schema_version=header.get("schema_version"),
            counts=counts,
            overwrites=overwrites,
            is_delta=bool(header.get("delta")),
            delta_since=_parse_datetime(header.get("since")),
        )
        db.add(result)
        db.flush()
        _pre_commit_hook()
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("snapshot_import_failed")
        raise

    logger.info("snapshot_imported", import_id=result.id, counts=counts)
    return result
