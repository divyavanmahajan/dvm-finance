"""URL-round-trippable transaction filter model and SQL query builder.

Golden Principle 8: filter state lives entirely in the URL query string. This
module is the single source of truth for parsing that query string into a typed
:class:`TransactionFilter`, serialising it back, resolving date presets, and
building the corresponding indexed SQLAlchemy query.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any
from urllib.parse import parse_qsl, urlencode

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Query, Session

from ..constants import is_transfer_category
from .models import Transaction
from .utils import CATEGORY_SEPARATOR

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PAGE_SIZE = 50

PRESETS = ("this-month", "last-month", "this-year", "last-year")

UNCATEGORIZED = "uncategorized"

# sort key -> (column, descending)
_SORTS: dict[str, tuple[Any, bool]] = {
    "date_desc": (Transaction.transactiondate, True),
    "date_asc": (Transaction.transactiondate, False),
    "amount_desc": (Transaction.amount, True),
    "amount_asc": (Transaction.amount, False),
    "category_desc": (func.coalesce(Transaction.manual_category, Transaction.category), True),
    "category_asc": (func.coalesce(Transaction.manual_category, Transaction.category), False),
}
DEFAULT_SORT = "date_desc"


def _effective_category_expr():
    return func.coalesce(
        func.nullif(Transaction.manual_category, ""), Transaction.category
    )


def _effective_tags_expr():
    return func.coalesce(func.nullif(Transaction.manual_tags, ""), Transaction.tags)


# ---------------------------------------------------------------------------
# Preset date ranges
# ---------------------------------------------------------------------------


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def resolve_preset_range(preset: str, today: date | None = None) -> tuple[date, date]:
    """Resolve a named preset into an inclusive (from, to) date range."""
    today = today or date.today()
    if preset == "this-month":
        return date(today.year, today.month, 1), _month_end(today.year, today.month)
    if preset == "last-month":
        year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        return date(year, month, 1), _month_end(year, month)
    if preset == "this-year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    if preset == "last-year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    raise ValueError(f"Unknown preset: {preset!r}")


# ---------------------------------------------------------------------------
# Filter model
# ---------------------------------------------------------------------------


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@dataclass
class TransactionFilter:
    """Typed representation of the transaction filter query string."""

    q: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    preset: str | None = None
    categories: list[str] = field(default_factory=list)
    exclude_categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    accounts: list[str] = field(default_factory=list)
    amount_min: float | None = None
    amount_max: float | None = None
    rule_id: int | None = None
    source_file: str | None = None
    include_transfers: bool = False
    sort: str = DEFAULT_SORT
    page: int = 1

    # -- construction --------------------------------------------------------

    @classmethod
    def _build(cls, one, many) -> TransactionFilter:
        sort = one("sort") or DEFAULT_SORT
        if sort not in _SORTS:
            sort = DEFAULT_SORT
        page = _parse_int(one("page")) or 1
        if page < 1:
            page = 1
        preset = one("preset")
        if preset not in PRESETS:
            preset = None
        # Parse include_transfers: True if param is "1", "true", or "True"; False otherwise
        include_transfers_str = one("include_transfers") or ""
        include_transfers = include_transfers_str in ("1", "true", "True")
        return cls(
            q=(one("q") or None),
            date_from=_parse_date(one("date_from")),
            date_to=_parse_date(one("date_to")),
            preset=preset,
            categories=[c for c in many("category") if c],
            exclude_categories=[c for c in many("exclude_category") if c],
            tags=[t for t in many("tag") if t],
            accounts=[a for a in many("account") if a],
            amount_min=_parse_float(one("amount_min")),
            amount_max=_parse_float(one("amount_max")),
            rule_id=_parse_int(one("rule_id")),
            source_file=(one("source_file") or None),
            include_transfers=include_transfers,
            sort=sort,
            page=page,
        )

    @classmethod
    def from_params(cls, params) -> TransactionFilter:
        """Build from a Starlette ``QueryParams`` (or any getlist/get mapping)."""
        return cls._build(params.get, params.getlist)

    @classmethod
    def from_query_string(cls, qs: str) -> TransactionFilter:
        raw: dict[str, list[str]] = {}
        for key, value in parse_qsl(qs, keep_blank_values=False):
            raw.setdefault(key, []).append(value)

        def one(key: str) -> str | None:
            values = raw.get(key)
            return values[-1] if values else None

        def many(key: str) -> list[str]:
            return raw.get(key, [])

        return cls._build(one, many)

    # -- serialisation -------------------------------------------------------

    def to_pairs(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        if self.q:
            pairs.append(("q", self.q))
        if self.date_from:
            pairs.append(("date_from", self.date_from.isoformat()))
        if self.date_to:
            pairs.append(("date_to", self.date_to.isoformat()))
        if self.preset:
            pairs.append(("preset", self.preset))
        for c in self.categories:
            pairs.append(("category", c))
        for c in self.exclude_categories:
            pairs.append(("exclude_category", c))
        for t in self.tags:
            pairs.append(("tag", t))
        for a in self.accounts:
            pairs.append(("account", a))
        if self.amount_min is not None:
            pairs.append(("amount_min", _num(self.amount_min)))
        if self.amount_max is not None:
            pairs.append(("amount_max", _num(self.amount_max)))
        if self.rule_id is not None:
            pairs.append(("rule_id", str(self.rule_id)))
        if self.source_file:
            pairs.append(("source_file", self.source_file))
        if self.include_transfers:
            pairs.append(("include_transfers", "1"))
        if self.sort != DEFAULT_SORT:
            pairs.append(("sort", self.sort))
        if self.page != 1:
            pairs.append(("page", str(self.page)))
        return pairs

    def to_query_string(self) -> str:
        return urlencode(self.to_pairs())

    # -- derived helpers -----------------------------------------------------

    def effective_dates(self, today: date | None = None) -> tuple[date | None, date | None]:
        """Return the (from, to) range, resolving a preset if one is set."""
        if self.preset:
            return resolve_preset_range(self.preset, today)
        return self.date_from, self.date_to

    def with_page(self, page: int) -> TransactionFilter:
        return replace(self, page=page)

    def with_sort(self, sort: str) -> TransactionFilter:
        return replace(self, sort=sort, page=1)

    def without(self, kind: str, value: str | None = None) -> str:
        """Return the query string with one active filter removed."""
        new = self._removed(kind, value)
        return new.to_query_string()

    def _removed(self, kind: str, value: str | None) -> TransactionFilter:
        f = replace(self, categories=list(self.categories),
                    exclude_categories=list(self.exclude_categories),
                    tags=list(self.tags), accounts=list(self.accounts), page=1)
        if kind == "q":
            f.q = None
        elif kind == "date":
            f.date_from = f.date_to = f.preset = None
        elif kind == "category" and value is not None:
            f.categories = [c for c in f.categories if c != value]
        elif kind == "exclude_category" and value is not None:
            f.exclude_categories = [c for c in f.exclude_categories if c != value]
        elif kind == "tag" and value is not None:
            f.tags = [t for t in f.tags if t != value]
        elif kind == "account" and value is not None:
            f.accounts = [a for a in f.accounts if a != value]
        elif kind == "amount":
            f.amount_min = f.amount_max = None
        elif kind == "rule_id":
            f.rule_id = None
        elif kind == "source_file":
            f.source_file = None
        return f

    def active_chips(self) -> list[dict[str, str]]:
        """A flat list of removable active-filter chips for the UI."""
        chips: list[dict[str, str]] = []
        if self.q:
            chips.append({"kind": "q", "value": self.q, "label": f"Search: {self.q}",
                          "remove": self.without("q")})
        if self.preset:
            chips.append({"kind": "date", "value": self.preset,
                          "label": self.preset.replace("-", " ").title(),
                          "remove": self.without("date")})
        elif self.date_from or self.date_to:
            lo = self.date_from.isoformat() if self.date_from else "…"
            hi = self.date_to.isoformat() if self.date_to else "…"
            chips.append({"kind": "date", "value": "range", "label": f"{lo} → {hi}",
                          "remove": self.without("date")})
        for c in self.categories:
            label = "Uncategorized" if c == UNCATEGORIZED else c
            chips.append({"kind": "category", "value": c, "label": f"Category: {label}",
                          "remove": self.without("category", c)})
        for c in self.exclude_categories:
            label = "Uncategorized" if c == UNCATEGORIZED else c
            chips.append({"kind": "exclude_category", "value": c,
                          "label": f"Exclude: {label}",
                          "remove": self.without("exclude_category", c)})
        for t in self.tags:
            chips.append({"kind": "tag", "value": t, "label": f"Tag: {t}",
                          "remove": self.without("tag", t)})
        for a in self.accounts:
            chips.append({"kind": "account", "value": a, "label": f"Account: {a}",
                          "remove": self.without("account", a)})
        if self.amount_min is not None or self.amount_max is not None:
            lo = _num(self.amount_min) if self.amount_min is not None else "0"
            hi = _num(self.amount_max) if self.amount_max is not None else "∞"
            chips.append({"kind": "amount", "value": "range", "label": f"Amount {lo}–{hi}",
                          "remove": self.without("amount")})
        if self.rule_id is not None:
            chips.append({"kind": "rule_id", "value": str(self.rule_id),
                          "label": f"Rule #{self.rule_id}", "remove": self.without("rule_id")})
        if self.source_file:
            chips.append({"kind": "source_file", "value": self.source_file,
                          "label": f"File: {self.source_file}",
                          "remove": self.without("source_file")})
        return chips


def _num(value: float) -> str:
    """Render a float without a trailing ``.0`` for whole numbers."""
    if value == int(value):
        return str(int(value))
    return str(value)


# ---------------------------------------------------------------------------
# SQL query building
# ---------------------------------------------------------------------------


def build_query(db: Session, f: TransactionFilter, today: date | None = None) -> Query:
    """Build the filtered (unpaginated, unsorted) transaction query."""
    query = db.query(Transaction)
    eff_cat = _effective_category_expr()
    eff_tags = _effective_tags_expr()

    if f.q:
        like = f"%{f.q}%"
        query = query.filter(
            or_(
                Transaction.description.ilike(like),
                Transaction.description_structured.ilike(like),
            )
        )

    lo, hi = f.effective_dates(today)
    if lo:
        query = query.filter(Transaction.transactiondate >= lo)
    if hi:
        query = query.filter(Transaction.transactiondate <= hi)

    # Exclude transfers by default (unless include_transfers is True)
    if not f.include_transfers:
        # Exclude transactions whose effective category contains 'transfer' (case-insensitive)
        query = query.filter(
            or_(eff_cat.is_(None), eff_cat == "", ~eff_cat.ilike('%transfer%'))
        )

    def _category_cond(cat: str):
        """Match a category exactly or any hierarchical child (hyphen-separated)."""
        if cat == UNCATEGORIZED:
            return or_(eff_cat.is_(None), eff_cat == "")
        c = cat.lower()
        return or_(
            func.lower(eff_cat) == c,
            func.lower(eff_cat).like(f"{c}{CATEGORY_SEPARATOR}%"),
        )

    if f.categories:
        query = query.filter(or_(*[_category_cond(cat) for cat in f.categories]))

    if f.exclude_categories:
        for cat in f.exclude_categories:
            if cat == UNCATEGORIZED:
                query = query.filter(~_category_cond(cat))
            else:
                # NOT LIKE is NULL for uncategorized rows; keep them explicitly.
                query = query.filter(
                    or_(eff_cat.is_(None), eff_cat == "", ~_category_cond(cat))
                )

    if f.tags:
        conds = [eff_tags.ilike(f"%{tag}%") for tag in f.tags]
        query = query.filter(or_(*conds))

    if f.accounts:
        query = query.filter(Transaction.accountNumber.in_(f.accounts))

    if f.amount_min is not None or f.amount_max is not None:
        abs_amount = func.abs(Transaction.amount)
        if f.amount_min is not None and f.amount_max is not None:
            query = query.filter(and_(abs_amount >= f.amount_min, abs_amount <= f.amount_max))
        elif f.amount_min is not None:
            query = query.filter(abs_amount >= f.amount_min)
        else:
            query = query.filter(abs_amount <= f.amount_max)

    if f.rule_id is not None:
        query = query.filter(Transaction.categorization_source == str(f.rule_id))

    if f.source_file:
        query = query.filter(Transaction.source_file == f.source_file)

    return query


def apply_sort(query: Query, f: TransactionFilter) -> Query:
    column, descending = _SORTS.get(f.sort, _SORTS[DEFAULT_SORT])
    if descending:
        return query.order_by(column.desc(), Transaction.id.desc())
    return query.order_by(column.asc(), Transaction.id.asc())


@dataclass
class Page:
    items: list[Transaction]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        if self.total == 0:
            return 1
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def start_index(self) -> int:
        if self.total == 0:
            return 0
        return (self.page - 1) * self.page_size + 1

    @property
    def end_index(self) -> int:
        return min(self.page * self.page_size, self.total)


def paginate(db: Session, f: TransactionFilter, today: date | None = None,
             page_size: int = PAGE_SIZE) -> Page:
    """Run the filtered/sorted query with server-side pagination."""
    base = build_query(db, f, today)
    total = base.order_by(None).count()
    page = f.page
    max_page = max(1, (total + page_size - 1) // page_size) if total else 1
    if page > max_page:
        page = max_page
    ordered = apply_sort(base, f)
    items = ordered.offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=items, total=total, page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# Effective category/tags for display (manual precedence)
# ---------------------------------------------------------------------------


def effective_category(txn: Transaction) -> str | None:
    if txn.manual_category:
        return txn.manual_category
    return txn.category


def effective_tags(txn: Transaction) -> str | None:
    if txn.manual_tags:
        return txn.manual_tags
    return txn.tags


def is_manual(txn: Transaction) -> bool:
    return txn.categorization_source == "manual" or bool(txn.manual_category)
