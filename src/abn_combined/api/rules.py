"""Rules UI: priority-ordered list, editor with dynamic conditions, draft preview,
create-from-transaction prefill, history of change reports, recategorize-all.

Every mutation (create/update/delete/toggle/recategorize) goes through
``record_rule_change`` — Golden Principle 5: no silent recategorization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.categorizer import (
    RuleValidationError,
    preview_rule,
    record_rule_change,
    rule_snapshot,
    validate_rule_regex,
)
from ..core.models import (
    CategorizationRule,
    RuleChangeReport,
    RuleCondition,
    Transaction,
)
from ..core.rule_prefill import blank_rule_vm, prefill_rule_from_transaction
from ..core.utils import normalize_category
from ..db import get_db
from ..logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)

VALID_RULE_TYPES = ["keyword", "account_iban", "structured_field", "full_description"]
VALID_PATTERNS = ["contains", "exact", "starts_with", "ends_with", "regex"]
VALID_OPERATORS = ["AND", "OR"]

# Common structured-description fields offered in field-target datalists.
FIELD_TARGET_SUGGESTIONS = [
    "description", "name", "iban", "payer_iban", "merchant_name", "merchant_code",
    "counterparty", "transaction_type", "format", "omschrijving", "kenmerk",
]


def _templates(request: Request):
    from ..app import templates

    return templates


# ---------------------------------------------------------------------------
# Draft rule (transient, never touches the session) for preview / validation
# ---------------------------------------------------------------------------


@dataclass
class DraftCondition:
    field_target: str
    match_pattern: str
    match_value: str
    operator: str = "AND"
    sort_order: int = 0


@dataclass
class DraftRule:
    rule_type: str
    match_pattern: str
    match_value: str
    category: str | None = None
    field_target: str | None = None
    tags: str | None = None
    priority: int = 100
    is_active: bool = True
    notes: str | None = None
    filter_account: str | None = None
    filter_currency: str | None = None
    filter_date_from: date | None = None
    filter_date_to: date | None = None
    conditions: list[DraftCondition] = field(default_factory=list)
    id: int | None = None


# ---------------------------------------------------------------------------
# Form parsing + validation
# ---------------------------------------------------------------------------


def _parse_date(value: str | None, name: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid date for {name}. Use YYYY-MM-DD."
        ) from exc


async def _parse_rule_form(request: Request) -> dict[str, Any]:
    """Parse the rule editor form into a view-model dict (same shape as blank_rule_vm)."""
    form = await request.form()
    vm = blank_rule_vm()
    for key in ("rule_type", "match_pattern", "field_target", "match_value", "category",
                "tags", "notes", "filter_account", "filter_currency",
                "filter_date_from", "filter_date_to"):
        vm[key] = (form.get(key) or "").strip()
    try:
        vm["priority"] = int(form.get("priority") or 100)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="priority must be an integer") from exc
    vm["is_active"] = form.get("is_active") in ("on", "true", "1", "True")

    fields = form.getlist("cond_field_target")
    patterns = form.getlist("cond_match_pattern")
    values = form.getlist("cond_match_value")
    operators = form.getlist("cond_operator")
    orders = form.getlist("cond_sort_order")
    conditions = []
    for i in range(len(fields)):
        ft = (fields[i] or "").strip()
        mv = (values[i] if i < len(values) else "").strip()
        if not ft and not mv:
            continue  # blank row
        try:
            order = int(orders[i]) if i < len(orders) and orders[i] != "" else i
        except ValueError:
            order = i
        conditions.append({
            "field_target": ft,
            "match_pattern": (patterns[i] if i < len(patterns) else "contains") or "contains",
            "match_value": mv,
            "operator": ((operators[i] if i < len(operators) else "AND") or "AND").upper(),
            "sort_order": order,
        })
    conditions.sort(key=lambda c: c["sort_order"])
    vm["conditions"] = conditions
    return vm


def _validate_vm(vm: dict[str, Any], require_category: bool = True) -> list[str]:
    errors = []
    if vm["rule_type"] not in VALID_RULE_TYPES:
        errors.append(f"rule_type must be one of: {', '.join(VALID_RULE_TYPES)}")
    if vm["match_pattern"] not in VALID_PATTERNS:
        errors.append(f"match_pattern must be one of: {', '.join(VALID_PATTERNS)}")
    if not vm["match_value"]:
        errors.append("match_value is required")
    if require_category and not vm["category"]:
        errors.append("category is required")
    for i, cond in enumerate(vm["conditions"]):
        if not cond["field_target"] or not cond["match_value"]:
            errors.append(f"condition {i + 1}: field and value are required")
        if cond["match_pattern"] not in VALID_PATTERNS:
            errors.append(f"condition {i + 1}: invalid match pattern")
        if cond["operator"] not in VALID_OPERATORS:
            errors.append(f"condition {i + 1}: operator must be AND or OR")
    try:
        validate_rule_regex(_vm_to_draft(vm))
    except RuleValidationError as exc:
        errors.append(str(exc))
    return errors


def _vm_to_draft(vm: dict[str, Any], rule_id: int | None = None) -> DraftRule:
    return DraftRule(
        rule_type=vm["rule_type"],
        match_pattern=vm["match_pattern"],
        field_target=vm["field_target"] or None,
        match_value=vm["match_value"],
        category=normalize_category(vm["category"]) or vm["category"] or None,
        tags=vm["tags"] or None,
        priority=vm["priority"],
        is_active=vm["is_active"],
        notes=vm["notes"] or None,
        filter_account=vm["filter_account"] or None,
        filter_currency=vm["filter_currency"] or None,
        filter_date_from=_parse_date(vm["filter_date_from"], "filter_date_from"),
        filter_date_to=_parse_date(vm["filter_date_to"], "filter_date_to"),
        conditions=[
            DraftCondition(
                field_target=c["field_target"],
                match_pattern=c["match_pattern"],
                match_value=c["match_value"],
                operator=c["operator"],
                sort_order=c["sort_order"],
            )
            for c in vm["conditions"]
        ],
        id=rule_id,
    )


def _apply_vm_to_rule(rule: CategorizationRule, vm: dict[str, Any]) -> None:
    rule.priority = vm["priority"]
    rule.rule_type = vm["rule_type"]
    rule.match_pattern = vm["match_pattern"]
    rule.field_target = vm["field_target"] or None
    rule.match_value = vm["match_value"]
    rule.category = normalize_category(vm["category"]) or vm["category"]
    rule.tags = vm["tags"] or None
    rule.is_active = vm["is_active"]
    rule.notes = vm["notes"] or None
    rule.filter_account = vm["filter_account"] or None
    rule.filter_currency = vm["filter_currency"] or None
    rule.filter_date_from = _parse_date(vm["filter_date_from"], "filter_date_from")
    rule.filter_date_to = _parse_date(vm["filter_date_to"], "filter_date_to")
    # Replace conditions wholesale (delete-orphan cascade removes the old rows).
    rule.conditions.clear()
    for c in vm["conditions"]:
        rule.conditions.append(RuleCondition(
            field_target=c["field_target"],
            match_pattern=c["match_pattern"],
            match_value=c["match_value"],
            operator=c["operator"],
            sort_order=c["sort_order"],
        ))


def _rule_to_vm(rule: CategorizationRule) -> dict[str, Any]:
    vm = blank_rule_vm()
    vm.update({
        "id": rule.id,
        "uuid": rule.uuid,
        "priority": rule.priority,
        "rule_type": rule.rule_type,
        "match_pattern": rule.match_pattern,
        "field_target": rule.field_target or "",
        "match_value": rule.match_value,
        "category": rule.category or "",
        "tags": rule.tags or "",
        "is_active": rule.is_active,
        "notes": rule.notes or "",
        "filter_account": rule.filter_account or "",
        "filter_currency": rule.filter_currency or "",
        "filter_date_from": rule.filter_date_from.isoformat() if rule.filter_date_from else "",
        "filter_date_to": rule.filter_date_to.isoformat() if rule.filter_date_to else "",
        "conditions": [
            {
                "field_target": c.field_target,
                "match_pattern": c.match_pattern,
                "match_value": c.match_value,
                "operator": c.operator,
                "sort_order": c.sort_order,
            }
            for c in rule.conditions
        ],
    })
    return vm


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _get_rule_or_404(db: Session, rule_id: int) -> CategorizationRule:
    rule = db.get(CategorizationRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


def _matched_counts(db: Session) -> dict[int, int]:
    """Transactions currently attributed per rule (categorization_source = str(id))."""
    rows = (
        db.query(Transaction.categorization_source, func.count(Transaction.id))
        .filter(Transaction.categorization_source.isnot(None))
        .group_by(Transaction.categorization_source)
        .all()
    )
    counts: dict[int, int] = {}
    for source, n in rows:
        try:
            counts[int(source)] = n
        except (TypeError, ValueError):
            continue
    return counts


def _known_accounts(db: Session) -> list[str]:
    rows = db.query(Transaction.accountNumber).distinct().all()
    return sorted({r[0] for r in rows if r[0]})


def _known_categories(db: Session) -> list[str]:
    cats: set[str] = set()
    for col in (Transaction.category, Transaction.manual_category):
        for (value,) in db.query(col).distinct():
            if value:
                cats.add(value)
    for (value,) in db.query(CategorizationRule.category).distinct():
        if value:
            cats.add(value.lower())
    return sorted(cats)


def _editor_context(request: Request, db: Session, vm: dict[str, Any], *,
                    auto_preview: bool = False, errors: list[str] | None = None) -> dict:
    return {
        "request": request,
        "active_path": "/rules",
        "title": "Edit rule" if vm.get("id") else "New rule",
        "vm": vm,
        "rule_types": VALID_RULE_TYPES,
        "patterns": VALID_PATTERNS,
        "operators": VALID_OPERATORS,
        "field_suggestions": FIELD_TARGET_SUGGESTIONS,
        "accounts": _known_accounts(db),
        "categories": _known_categories(db),
        "auto_preview": auto_preview,
        "errors": errors or [],
    }


def _render_editor(request: Request, db: Session, vm: dict[str, Any], *,
                   auto_preview: bool = False, errors: list[str] | None = None,
                   status_code: int = 200) -> HTMLResponse:
    ctx = _editor_context(request, db, vm, auto_preview=auto_preview, errors=errors)
    return _templates(request).TemplateResponse(
        request, "rules_edit.html", ctx, status_code=status_code
    )


# ---------------------------------------------------------------------------
# History report view-models (shape shared with step-11 snapshot imports)
# ---------------------------------------------------------------------------

_SNAPSHOT_DIFF_FIELDS = [
    "priority", "rule_type", "match_pattern", "field_target", "match_value",
    "category", "tags", "is_active", "notes", "filter_account", "filter_currency",
    "filter_date_from", "filter_date_to", "conditions",
]


def _conds_str(conds: Any) -> str:
    if not conds:
        return ""
    return "; ".join(
        f"{c.get('operator', 'AND')} {c.get('field_target')} "
        f"{c.get('match_pattern')} '{c.get('match_value')}'"
        for c in conds
    )


def _snapshot_diff(before: dict | None, after: dict | None) -> list[dict[str, Any]]:
    diff = []
    for key in _SNAPSHOT_DIFF_FIELDS:
        b = (before or {}).get(key)
        a = (after or {}).get(key)
        if key == "conditions":
            b, a = _conds_str(b), _conds_str(a)
        if b != a:
            diff.append({"field": key, "before": b, "after": a})
    return diff


def _txn_link(txn: Transaction | None) -> str | None:
    if txn is None or not txn.description:
        return None
    return f"/transactions?q={quote(txn.description[:60])}"


def _report_vm(db: Session, report: RuleChangeReport) -> dict[str, Any]:
    """A generic, template-ready view of one change report.

    Deliberately a plain dict so step 11 (snapshot import reports) can render in the
    same ``_rule_report.html`` partial by building the same shape.
    """
    snap = report.rule_after or report.rule_before or {}
    label = snap.get("category") or snap.get("match_value") or ""
    txn_ids = [i.transaction_id for i in report.items]
    txns = {}
    if txn_ids:
        txns = {
            t.id: t
            for t in db.query(Transaction).filter(Transaction.id.in_(txn_ids)).all()
        }
    items = [
        {
            "transaction_id": i.transaction_id,
            "description": (txns[i.transaction_id].description
                            if i.transaction_id in txns else None),
            "link": _txn_link(txns.get(i.transaction_id)),
            "old_category": i.old_category,
            "new_category": i.new_category,
            "old_tags": i.old_tags,
            "new_tags": i.new_tags,
        }
        for i in report.items
    ]
    return {
        "id": report.id,
        "created_at": report.created_at,
        "action": report.action,
        "rule_id": report.rule_id,
        "rule_uuid": report.rule_uuid,
        "rule_label": label,
        "diff": _snapshot_diff(report.rule_before, report.rule_after),
        "summary": report.summary or {},
        # NB: named txn_changes (not "items") — dicts expose .items as a method in Jinja.
        "txn_changes": items,
    }


# ---------------------------------------------------------------------------
# Routes: list page
# ---------------------------------------------------------------------------


def _row_context(request: Request, db: Session, rule: CategorizationRule) -> dict:
    return {
        "request": request,
        "rule": rule,
        "count": _matched_counts(db).get(rule.id, 0),
    }


@router.get("/rules", response_class=HTMLResponse, include_in_schema=False)
def rules_list(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    rules = (
        db.query(CategorizationRule)
        .order_by(CategorizationRule.priority.asc(), CategorizationRule.id.asc())
        .all()
    )
    counts = _matched_counts(db)
    ctx = {
        "request": request,
        "active_path": "/rules",
        "title": "Rules",
        "rules": rules,
        "counts": counts,
    }
    return _templates(request).TemplateResponse(request, "rules.html", ctx)


# ---------------------------------------------------------------------------
# Routes: editor pages (before /rules/{rule_id} so 'new'/'history' don't collide)
# ---------------------------------------------------------------------------


@router.get("/rules/new", response_class=HTMLResponse, include_in_schema=False)
def rule_new(request: Request, from_transaction: str | None = None,
             db: Session = Depends(get_db)) -> HTMLResponse:
    if from_transaction:
        txn = db.get(Transaction, from_transaction)
        if txn is None:
            raise HTTPException(status_code=404, detail="Transaction not found")
        vm = prefill_rule_from_transaction(txn)
        return _render_editor(request, db, vm, auto_preview=True)
    return _render_editor(request, db, blank_rule_vm())


@router.get("/rules/history", response_class=HTMLResponse, include_in_schema=False)
def rules_history(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    reports = (
        db.query(RuleChangeReport)
        .order_by(RuleChangeReport.created_at.desc(), RuleChangeReport.id.desc())
        .all()
    )
    ctx = {
        "request": request,
        "active_path": "/rules",
        "title": "Rule history",
        "reports": [_report_vm(db, r) for r in reports],
        "scope_rule_id": None,
    }
    return _templates(request).TemplateResponse(request, "rules_history.html", ctx)


@router.get("/rules/{rule_id}/history", response_class=HTMLResponse, include_in_schema=False)
def rule_history(request: Request, rule_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    rule = db.get(CategorizationRule, rule_id)  # may be deleted; history still valid
    query = db.query(RuleChangeReport).filter(RuleChangeReport.rule_id == rule_id)
    if rule is not None:
        query = db.query(RuleChangeReport).filter(
            (RuleChangeReport.rule_id == rule_id)
            | (RuleChangeReport.rule_uuid == rule.uuid)
        )
    reports = query.order_by(
        RuleChangeReport.created_at.desc(), RuleChangeReport.id.desc()
    ).all()
    ctx = {
        "request": request,
        "active_path": "/rules",
        "title": f"History — rule #{rule_id}",
        "reports": [_report_vm(db, r) for r in reports],
        "scope_rule_id": rule_id,
    }
    return _templates(request).TemplateResponse(request, "rules_history.html", ctx)


@router.get("/rules/{rule_id}/edit", response_class=HTMLResponse, include_in_schema=False)
def rule_edit(request: Request, rule_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    rule = _get_rule_or_404(db, rule_id)
    return _render_editor(request, db, _rule_to_vm(rule))


@router.get("/rules/{rule_id}", include_in_schema=False)
def rule_detail_redirect(rule_id: int) -> RedirectResponse:
    return RedirectResponse(url=f"/rules/{rule_id}/edit", status_code=303)


# ---------------------------------------------------------------------------
# Routes: preview (draft — works before the rule exists)
# ---------------------------------------------------------------------------


@router.post("/rules/preview", response_class=HTMLResponse, include_in_schema=False)
async def rule_preview(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    vm = await _parse_rule_form(request)
    form = await request.form()
    rule_id_raw = form.get("rule_id")
    rule_id = int(rule_id_raw) if rule_id_raw not in (None, "") else None

    tpl = _templates(request)
    if not vm["match_value"]:
        return tpl.TemplateResponse(
            request, "_rule_preview.html",
            {"request": request, "error": "Enter a match value to preview.", "preview": None},
        )
    try:
        draft = _vm_to_draft(vm, rule_id=rule_id)
        result = preview_rule(db, draft, existing_rule_id=rule_id)
    except RuleValidationError as exc:
        return tpl.TemplateResponse(
            request, "_rule_preview.html",
            {"request": request, "error": str(exc), "preview": None},
        )

    def _txns(ids: list[str], limit: int = 100) -> list[Transaction]:
        if not ids:
            return []
        shown = ids[:limit]
        txns = db.query(Transaction).filter(Transaction.id.in_(shown)).all()
        order = {tid: i for i, tid in enumerate(shown)}
        return sorted(txns, key=lambda t: order.get(t.id, 0))

    txn_by_id = {
        t.id: t
        for t in _txns(list({c.transaction_id for c in result.changes})[:100])
    }
    ctx = {
        "request": request,
        "error": None,
        "preview": result.as_dict(),
        "is_edit": rule_id is not None,
        "matched_txns": _txns(result.matched),
        "gained_txns": _txns(result.gains),
        "lost_txns": _txns(result.losses),
        "changes": [
            {
                "change": c,
                "txn": txn_by_id.get(c.transaction_id),
            }
            for c in result.changes[:100]
        ],
    }
    return tpl.TemplateResponse(request, "_rule_preview.html", ctx)


# ---------------------------------------------------------------------------
# Routes: mutations — all through record_rule_change (Golden Principle 5)
# ---------------------------------------------------------------------------


@router.post("/rules", include_in_schema=False)
async def rule_create(request: Request, db: Session = Depends(get_db)):
    vm = await _parse_rule_form(request)
    errors = _validate_vm(vm)
    if errors:
        return _render_editor(request, db, vm, errors=errors, status_code=400)

    rule = CategorizationRule()
    _apply_vm_to_rule(rule, vm)
    db.add(rule)
    db.flush()  # assign id so apply_rules + snapshot see the new rule
    report = record_rule_change(db, "create", before=None, after=rule_snapshot(rule))
    logger.info("rule_created", rule_id=rule.id, report_id=report.id,
                changed=report.summary.get("changed"))
    return RedirectResponse(url="/rules", status_code=303)


@router.post("/rules/recategorize", include_in_schema=False)
def recategorize_all(db: Session = Depends(get_db)) -> RedirectResponse:
    report = record_rule_change(db, "recategorize")
    logger.info("recategorize_all", report_id=report.id,
                changed=report.summary.get("changed"))
    return RedirectResponse(url=f"/rules/history#report-{report.id}", status_code=303)


@router.post("/rules/{rule_id}", include_in_schema=False)
async def rule_update(request: Request, rule_id: int, db: Session = Depends(get_db)):
    rule = _get_rule_or_404(db, rule_id)
    vm = await _parse_rule_form(request)
    errors = _validate_vm(vm)
    if errors:
        vm["id"], vm["uuid"] = rule.id, rule.uuid
        return _render_editor(request, db, vm, errors=errors, status_code=400)

    before = rule_snapshot(rule)
    _apply_vm_to_rule(rule, vm)
    db.flush()
    report = record_rule_change(db, "update", before=before, after=rule_snapshot(rule))
    logger.info("rule_updated", rule_id=rule.id, report_id=report.id,
                changed=report.summary.get("changed"))
    return RedirectResponse(url="/rules", status_code=303)


@router.post("/rules/{rule_id}/toggle", response_class=HTMLResponse, include_in_schema=False)
def rule_toggle(request: Request, rule_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    rule = _get_rule_or_404(db, rule_id)
    before = rule_snapshot(rule)
    rule.is_active = not rule.is_active
    db.flush()
    report = record_rule_change(db, "toggle", before=before, after=rule_snapshot(rule))
    logger.info("rule_toggled", rule_id=rule.id, active=rule.is_active,
                report_id=report.id)
    ctx = _row_context(request, db, rule)
    return _templates(request).TemplateResponse(request, "_rules_row.html", ctx)


@router.delete("/rules/{rule_id}", response_class=HTMLResponse, include_in_schema=False)
def rule_delete(request: Request, rule_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    rule = _get_rule_or_404(db, rule_id)
    before = rule_snapshot(rule)
    db.delete(rule)
    db.flush()
    report = record_rule_change(db, "delete", before=before, after=None,
                                rule_id=rule_id, rule_uuid=before.get("uuid"))
    logger.info("rule_deleted", rule_id=rule_id, report_id=report.id,
                changed=report.summary.get("changed"))
    # htmx removes the row (hx-swap="outerHTML" with empty body).
    return HTMLResponse("")
