"""Category-trends aggregation: effective category × period, SQL GROUP BY.

FR3 — the Trends tab. Aggregation happens in one ``GROUP BY`` query (NFR2);
Python only arranges the grouped rows into the hierarchical table structure.

Hierarchy convention: the legacy ``abn_analyst.db`` uses a **hyphen** separator
(``groceries-ah``, ``education-tuition-violin``). The top-level segment is the
parent; every distinct full category value becomes a sub-row under it. Because
the transactions filter (:mod:`.filters`) prefix-matches on ``:`` — not ``-`` —
parent click-through links enumerate every exact category in the subtree as
repeated ``category=`` params, which the filter ORs together. That keeps
Golden Principle 8 intact: a cell is nothing more than a filtered-transactions
URL, and its linked transactions sum exactly to the cell value.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import parse_qsl

from sqlalchemy import func
from sqlalchemy.orm import Session

from .filters import UNCATEGORIZED, TransactionFilter, _parse_date
from .models import Transaction
from .utils import CATEGORY_SEPARATOR as SEPARATOR

UNCATEGORIZED_LABEL = "Uncategorized"

GRANULARITIES = ("month", "year")
DEFAULT_GRANULARITY = "month"

_MONTH_LABELS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def default_window(today: date | None = None) -> tuple[date, date]:
    """The default date window: the last 12 full months (current month excluded)."""
    today = today or date.today()
    end_year, end_month = _shift_month(today.year, today.month, -1)
    start_year, start_month = _shift_month(end_year, end_month, -11)
    return date(start_year, start_month, 1), _month_end(end_year, end_month)


# ---------------------------------------------------------------------------
# URL-state params (same style as core/filters.py)
# ---------------------------------------------------------------------------


TRENDS_SORTS = ("category_asc", "category_desc", "total_asc", "total_desc")
DEFAULT_TRENDS_SORT = "category_asc"

# column key -> (asc sort key, desc sort key), for header click-to-sort toggling.
TRENDS_SORTABLE_COLUMNS: dict[str, tuple[str, str]] = {
    "category": ("category_asc", "category_desc"),
    "total": ("total_asc", "total_desc"),
}


def next_trends_sort(current_sort: str, column: str) -> str:
    asc_key, desc_key = TRENDS_SORTABLE_COLUMNS[column]
    if current_sort == asc_key:
        return desc_key
    return asc_key


@dataclass
class TrendsParams:
    """Typed representation of the /trends query string."""

    granularity: str = DEFAULT_GRANULARITY
    date_from: date | None = None
    date_to: date | None = None
    accounts: list[str] = field(default_factory=list)
    include_transfers: bool = False
    sort: str = DEFAULT_TRENDS_SORT

    @classmethod
    def _build(cls, one, many) -> TrendsParams:
        granularity = one("granularity") or DEFAULT_GRANULARITY
        if granularity not in GRANULARITIES:
            granularity = DEFAULT_GRANULARITY
        # Parse include_transfers: True if param is "1", "true", or "True"; False otherwise
        include_transfers_str = one("include_transfers") or ""
        include_transfers = include_transfers_str in ("1", "true", "True")
        sort = one("sort") or DEFAULT_TRENDS_SORT
        if sort not in TRENDS_SORTS:
            sort = DEFAULT_TRENDS_SORT
        return cls(
            granularity=granularity,
            date_from=_parse_date(one("date_from")),
            date_to=_parse_date(one("date_to")),
            accounts=[a for a in many("account") if a],
            include_transfers=include_transfers,
            sort=sort,
        )

    @classmethod
    def from_params(cls, params) -> TrendsParams:
        """Build from a Starlette ``QueryParams`` (or any get/getlist mapping)."""
        return cls._build(params.get, params.getlist)

    @classmethod
    def from_query_string(cls, qs: str) -> TrendsParams:
        raw: dict[str, list[str]] = {}
        for key, value in parse_qsl(qs, keep_blank_values=False):
            raw.setdefault(key, []).append(value)

        def one(key: str) -> str | None:
            values = raw.get(key)
            return values[-1] if values else None

        return cls._build(one, lambda key: raw.get(key, []))

    def to_pairs(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        if self.granularity != DEFAULT_GRANULARITY:
            pairs.append(("granularity", self.granularity))
        if self.date_from:
            pairs.append(("date_from", self.date_from.isoformat()))
        if self.date_to:
            pairs.append(("date_to", self.date_to.isoformat()))
        for a in self.accounts:
            pairs.append(("account", a))
        if self.include_transfers:
            pairs.append(("include_transfers", "1"))
        if self.sort != DEFAULT_TRENDS_SORT:
            pairs.append(("sort", self.sort))
        return pairs

    def to_query_string(self) -> str:
        from urllib.parse import urlencode

        return urlencode(self.to_pairs())

    def effective_window(self, today: date | None = None) -> tuple[date, date]:
        """The (from, to) window, defaulting each missing side to the last 12 full months."""
        lo, hi = default_window(today)
        return self.date_from or lo, self.date_to or hi

    def with_sort(self, sort: str) -> TrendsParams:
        from dataclasses import replace

        return replace(self, sort=sort)

    def sort_url_for_column(self, column: str) -> str:
        return self.with_sort(next_trends_sort(self.sort, column)).to_query_string()

    def sort_state_for_column(self, column: str) -> str | None:
        asc_key, desc_key = TRENDS_SORTABLE_COLUMNS[column]
        if self.sort == asc_key:
            return "asc"
        if self.sort == desc_key:
            return "desc"
        return None


# ---------------------------------------------------------------------------
# Table structure
# ---------------------------------------------------------------------------


@dataclass
class Period:
    key: str
    label: str
    start: date
    end: date


@dataclass
class TrendRow:
    label: str
    categories: list[str]
    cells: dict[str, float]
    total: float
    children: list[TrendRow] = field(default_factory=list)

    @property
    def has_children(self) -> bool:
        return bool(self.children)


@dataclass
class TrendsTable:
    periods: list[Period]
    rows: list[TrendRow]
    column_totals: dict[str, float]
    grand_total: float


def build_periods(window_from: date, window_to: date, granularity: str) -> list[Period]:
    """All periods covering the window, edge periods clamped to the window.

    Clamping matters for click-through correctness: a cell's link carries the
    period's (clamped) start/end so it never selects transactions outside the
    aggregated window.
    """
    periods: list[Period] = []
    if window_from > window_to:
        return periods
    if granularity == "year":
        for year in range(window_from.year, window_to.year + 1):
            periods.append(
                Period(
                    key=str(year),
                    label=str(year),
                    start=max(date(year, 1, 1), window_from),
                    end=min(date(year, 12, 31), window_to),
                )
            )
        return periods

    year, month = window_from.year, window_from.month
    while (year, month) <= (window_to.year, window_to.month):
        periods.append(
            Period(
                key=f"{year:04d}-{month:02d}",
                label=f"{_MONTH_LABELS[month - 1]} {year}",
                start=max(date(year, month, 1), window_from),
                end=min(_month_end(year, month), window_to),
            )
        )
        year, month = _shift_month(year, month, 1)
    return periods


# ---------------------------------------------------------------------------
# Aggregation (SQL GROUP BY)
# ---------------------------------------------------------------------------


def aggregate(db: Session, params: TrendsParams, today: date | None = None) -> TrendsTable:
    """Aggregate effective-category × period sums over the window."""
    window_from, window_to = params.effective_window(today)
    periods = build_periods(window_from, window_to, params.granularity)

    fmt = "%Y" if params.granularity == "year" else "%Y-%m"
    period_expr = func.strftime(fmt, Transaction.transactiondate)
    eff_cat = func.lower(
        func.coalesce(func.nullif(Transaction.manual_category, ""), Transaction.category)
    )

    query = (
        db.query(period_expr, eff_cat, func.sum(Transaction.amount))
        .filter(Transaction.transactiondate >= window_from)
        .filter(Transaction.transactiondate <= window_to)
    )
    if params.accounts:
        query = query.filter(Transaction.accountNumber.in_(params.accounts))
    # Exclude transfers by default (unless include_transfers is True)
    if not params.include_transfers:
        from sqlalchemy import or_
        query = query.filter(
            or_(eff_cat.is_(None), eff_cat == "", ~eff_cat.ilike('%transfer%'))
        )
    grouped = query.group_by(period_expr, eff_cat).all()

    # cat -> {period_key: amount}; None/"" categories fold into the uncategorized
    # bucket, so accumulate (SQL groups NULL and '' separately).
    by_cat: dict[str | None, dict[str, float]] = {}
    for period_key, cat, amount in grouped:
        cells = by_cat.setdefault(cat or None, {})
        cells[period_key] = cells.get(period_key, 0.0) + float(amount)

    uncategorized_cells = by_cat.pop(None, None)

    # Group full category values by their top-level (first hyphen segment) parent.
    groups: dict[str, list[str]] = {}
    for cat in by_cat:
        groups.setdefault(cat.split(SEPARATOR, 1)[0], []).append(cat)

    rows: list[TrendRow] = []
    for parent_label in sorted(groups):
        cats = sorted(groups[parent_label])
        if cats == [parent_label]:
            rows.append(_leaf_row(parent_label, by_cat[parent_label]))
            continue
        children = [_leaf_row(cat, by_cat[cat]) for cat in cats]
        parent_cells: dict[str, float] = {}
        for child in children:
            for key, amount in child.cells.items():
                parent_cells[key] = parent_cells.get(key, 0.0) + amount
        rows.append(
            TrendRow(
                label=parent_label,
                categories=cats,
                cells=parent_cells,
                total=sum(parent_cells.values()),
                children=children,
            )
        )

    if uncategorized_cells is not None:
        rows.append(
            TrendRow(
                label=UNCATEGORIZED_LABEL,
                categories=[UNCATEGORIZED],
                cells=uncategorized_cells,
                total=sum(uncategorized_cells.values()),
            )
        )

    column_totals: dict[str, float] = {}
    for row in rows:
        for key, amount in row.cells.items():
            column_totals[key] = column_totals.get(key, 0.0) + amount

    rows = _sort_rows(rows, params.sort)

    return TrendsTable(
        periods=periods,
        rows=rows,
        column_totals=column_totals,
        grand_total=sum(column_totals.values()),
    )


def _sort_rows(rows: list[TrendRow], sort: str) -> list[TrendRow]:
    """Sort top-level rows by category label or total, asc/desc.

    Children within a parent row stay alphabetically ordered — only the
    top-level row order (which "column" of the pivoted table each row
    belongs under) changes.
    """
    if sort == "total_asc":
        return sorted(rows, key=lambda r: r.total)
    if sort == "total_desc":
        return sorted(rows, key=lambda r: r.total, reverse=True)
    if sort == "category_desc":
        return sorted(rows, key=lambda r: r.label.lower(), reverse=True)
    # category_asc (default) — rows are already alphabetical from `sorted(groups)`,
    # but the uncategorized row is appended last, so re-sort for consistency.
    return sorted(rows, key=lambda r: r.label.lower())


def _leaf_row(cat: str, cells: dict[str, float]) -> TrendRow:
    return TrendRow(label=cat, categories=[cat], cells=cells, total=sum(cells.values()))


# ---------------------------------------------------------------------------
# Click-through links (Golden Principle 8: just a filtered-transactions URL)
# ---------------------------------------------------------------------------


def transactions_link(
    categories: list[str],
    date_from: date,
    date_to: date,
    accounts: list[str],
) -> str:
    """The /transactions URL selecting exactly the transactions behind a cell/row."""
    f = TransactionFilter(
        date_from=date_from,
        date_to=date_to,
        categories=list(categories),
        accounts=list(accounts),
    )
    return f"/transactions?{f.to_query_string()}"
