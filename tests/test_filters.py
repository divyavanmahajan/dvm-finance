"""Unit tests for the URL-round-trippable transaction filter model."""

from __future__ import annotations

from datetime import date

import pytest

from abn_combined.core.filters import TransactionFilter, resolve_preset_range


def _roundtrip(f: TransactionFilter) -> TransactionFilter:
    return TransactionFilter.from_query_string(f.to_query_string())


class TestRoundTrip:
    def test_empty_filter_roundtrips(self):
        f = TransactionFilter()
        assert _roundtrip(f) == f
        assert f.to_query_string() == ""

    def test_free_text(self):
        f = TransactionFilter(q="albert heijn")
        assert _roundtrip(f) == f
        assert "q=albert+heijn" in f.to_query_string()

    def test_custom_date_range(self):
        f = TransactionFilter(date_from=date(2024, 1, 1), date_to=date(2024, 3, 31))
        assert _roundtrip(f) == f

    def test_preset(self):
        f = TransactionFilter(preset="this-month")
        assert _roundtrip(f) == f

    def test_multi_categories_including_uncategorized(self):
        # Real data uses hyphen separators; roundtrip must preserve them
        f = TransactionFilter(categories=["food", "food-groceries", "uncategorized"])
        assert _roundtrip(f) == f

    def test_exclude_categories_roundtrip(self):
        f = TransactionFilter(exclude_categories=["housing", "food-restaurants"])
        assert _roundtrip(f) == f

    def test_exclude_categories_in_query_string(self):
        f = TransactionFilter(exclude_categories=["housing"])
        qs = f.to_query_string()
        assert "exclude_category=housing" in qs

    def test_exclude_category_from_params(self):
        from starlette.datastructures import QueryParams
        qp = QueryParams("exclude_category=food&exclude_category=housing")
        f = TransactionFilter.from_params(qp)
        assert f.exclude_categories == ["food", "housing"]

    def test_multi_tags(self):
        f = TransactionFilter(tags=["holiday", "work"])
        assert _roundtrip(f) == f

    def test_multi_accounts(self):
        f = TransactionFilter(accounts=["NL01", "NL02"])
        assert _roundtrip(f) == f

    def test_amount_range(self):
        f = TransactionFilter(amount_min=10.0, amount_max=250.5)
        assert _roundtrip(f) == f

    def test_rule_id(self):
        f = TransactionFilter(rule_id=42)
        assert _roundtrip(f) == f

    def test_source_file(self):
        f = TransactionFilter(source_file="statement.STA")
        assert _roundtrip(f) == f

    def test_sort_and_page(self):
        f = TransactionFilter(sort="amount_asc", page=3)
        assert _roundtrip(f) == f

    def test_kitchen_sink(self):
        f = TransactionFilter(
            q="tikkie",
            date_from=date(2023, 6, 1),
            date_to=date(2023, 6, 30),
            categories=["food", "uncategorized"],
            tags=["work"],
            accounts=["NL91ABNA0123"],
            amount_min=5.0,
            amount_max=100.0,
            rule_id=7,
            source_file="x.csv",
            sort="amount_desc",
            page=2,
        )
        assert _roundtrip(f) == f


class TestDefaultsAndNormalisation:
    def test_defaults(self):
        f = TransactionFilter()
        assert f.sort == "date_desc"
        assert f.page == 1
        assert f.categories == []

    def test_invalid_sort_falls_back(self):
        f = TransactionFilter.from_query_string("sort=bogus")
        assert f.sort == "date_desc"

    def test_page_min_one(self):
        f = TransactionFilter.from_query_string("page=0")
        assert f.page == 1
        f2 = TransactionFilter.from_query_string("page=-5")
        assert f2.page == 1

    def test_bad_amount_ignored(self):
        f = TransactionFilter.from_query_string("amount_min=abc")
        assert f.amount_min is None

    def test_from_params_multidict(self):
        from starlette.datastructures import QueryParams

        qp = QueryParams("category=food&category=work&account=NL01")
        f = TransactionFilter.from_params(qp)
        assert f.categories == ["food", "work"]
        assert f.accounts == ["NL01"]


class TestPresetRanges:
    def test_this_month(self):
        today = date(2024, 3, 15)
        lo, hi = resolve_preset_range("this-month", today)
        assert lo == date(2024, 3, 1)
        assert hi == date(2024, 3, 31)

    def test_last_month(self):
        today = date(2024, 3, 15)
        lo, hi = resolve_preset_range("last-month", today)
        assert lo == date(2024, 2, 1)
        assert hi == date(2024, 2, 29)

    def test_last_month_january_wraps(self):
        today = date(2024, 1, 10)
        lo, hi = resolve_preset_range("last-month", today)
        assert lo == date(2023, 12, 1)
        assert hi == date(2023, 12, 31)

    def test_this_year(self):
        today = date(2024, 7, 4)
        lo, hi = resolve_preset_range("this-year", today)
        assert lo == date(2024, 1, 1)
        assert hi == date(2024, 12, 31)

    def test_last_year(self):
        today = date(2024, 7, 4)
        lo, hi = resolve_preset_range("last-year", today)
        assert lo == date(2023, 1, 1)
        assert hi == date(2023, 12, 31)

    def test_effective_dates_prefers_preset(self):
        f = TransactionFilter(preset="this-year")
        lo, hi = f.effective_dates(today=date(2024, 5, 1))
        assert lo == date(2024, 1, 1)
        assert hi == date(2024, 12, 31)

    def test_effective_dates_custom(self):
        f = TransactionFilter(date_from=date(2024, 2, 2), date_to=date(2024, 2, 5))
        lo, hi = f.effective_dates(today=date(2024, 5, 1))
        assert lo == date(2024, 2, 2)
        assert hi == date(2024, 2, 5)


class TestChips:
    def test_active_chips_listed(self):
        f = TransactionFilter(q="ah", categories=["food"], rule_id=3)
        labels = {c["kind"] for c in f.active_chips()}
        assert "q" in labels
        assert "category" in labels
        assert "rule_id" in labels

    def test_remove_chip_returns_new_querystring(self):
        f = TransactionFilter(categories=["food", "work"], q="ah")
        qs = f.without("category", "food")
        f2 = TransactionFilter.from_query_string(qs)
        assert f2.categories == ["work"]
        assert f2.q == "ah"

    def test_no_chips_when_empty(self):
        assert TransactionFilter().active_chips() == []

    def test_exclude_category_chip_label(self):
        f = TransactionFilter(exclude_categories=["housing"])
        chips = f.active_chips()
        exclude_chips = [c for c in chips if c["kind"] == "exclude_category"]
        assert len(exclude_chips) == 1
        assert exclude_chips[0]["label"] == "Exclude: housing"

    def test_exclude_category_chip_remove(self):
        f = TransactionFilter(exclude_categories=["food", "housing"], q="test")
        qs = f.without("exclude_category", "food")
        f2 = TransactionFilter.from_query_string(qs)
        assert f2.exclude_categories == ["housing"]
        assert f2.q == "test"

    def test_exclude_uncategorized_chip_label(self):
        f = TransactionFilter(exclude_categories=["uncategorized"])
        chips = f.active_chips()
        exclude_chips = [c for c in chips if c["kind"] == "exclude_category"]
        assert exclude_chips[0]["label"] == "Exclude: Uncategorized"


@pytest.mark.parametrize(
    "sort",
    ["date_desc", "date_asc", "amount_desc", "amount_asc", "category_asc", "category_desc"],
)
def test_all_sorts_roundtrip(sort):
    f = TransactionFilter(sort=sort)
    assert TransactionFilter.from_query_string(f.to_query_string()).sort == sort
