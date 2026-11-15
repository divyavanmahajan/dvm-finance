"""The merge of the rows that the database already holds twice.

The bank writes one SEPA payment in two description forms, and the two forms
give two different transaction ids. A database from before the reference check
can therefore hold one payment twice. See
openspec/changes/unify-sepa-description-and-reference-dedup, group 8.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from abn_combined.core.merge import (
    merge_duplicates,
    preview_merge,
    undo_merge,
)
from abn_combined.core.models import Base, MergeReport, Transaction

REFERENCE = "KFF5Q4D85TQK39G6"
ACCOUNT = "720317081"


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'merge.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _row(
    db,
    row_id: str,
    *,
    reference: str | None = REFERENCE,
    account: str = ACCOUNT,
    structured_only: bool = False,
    **over,
) -> Transaction:
    """Write one row. ``structured_only`` models a row from before the backfill."""
    structured = None
    if reference is not None:
        structured = json.dumps(
            {"format": "sepa", "end_to_end_reference": reference}
        )
    values = dict(
        id=row_id,
        accountNumber=account,
        transactiondate=date(2024, 5, 19),
        amount=-5.75,
        description=f"form {row_id}",
        description_structured=structured,
        currency="EUR",
        end_to_end_reference=None if structured_only else reference,
    )
    values.update(over)
    row = Transaction(**values)
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------------------
# 8.1 The discovery of a group
# ---------------------------------------------------------------------------


def test_two_rows_of_one_account_make_a_group(db):
    _row(db, "aaa")
    _row(db, "bbb")

    preview = preview_merge(db)

    assert len(preview.groups) == 1
    assert preview.groups[0].reference == REFERENCE
    assert preview.groups[0].account == ACCOUNT


def test_two_accounts_make_no_group(db):
    """Task 8.1: a reference is unique for one creditor, not for the world."""
    _row(db, "aaa", account=ACCOUNT)
    _row(db, "bbb", account="123456789")

    assert preview_merge(db).groups == []


def test_nonref_makes_no_group(db):
    """Task 8.1: the bank writes NONREF when a payment holds no reference."""
    _row(db, "aaa", reference="NONREF")
    _row(db, "bbb", reference="NONREF")

    assert preview_merge(db).groups == []


def test_a_row_without_a_reference_makes_no_group(db):
    _row(db, "aaa", reference=None)
    _row(db, "bbb", reference=None)

    assert preview_merge(db).groups == []


def test_a_single_row_makes_no_group(db):
    _row(db, "aaa")

    assert preview_merge(db).groups == []


def test_a_row_from_before_the_backfill_joins_a_group(db):
    """The discovery also reads the structured description."""
    _row(db, "aaa", structured_only=True)
    _row(db, "bbb")

    assert len(preview_merge(db).groups) == 1


def test_an_already_merged_row_makes_no_group(db):
    """A merged row is not live, so a second run finds nothing."""
    _row(db, "aaa")
    _row(db, "bbb")
    merge_duplicates(db)

    assert preview_merge(db).groups == []


# ---------------------------------------------------------------------------
# 8.2 The survivor is the lowest id
# ---------------------------------------------------------------------------


def test_the_survivor_is_the_lowest_id(db):
    _row(db, "720317081_2024-05-19_-5.75_bbb")
    _row(db, "720317081_2024-05-19_-5.75_aaa")

    group = preview_merge(db).groups[0]

    assert group.survivor_id.endswith("aaa")
    assert group.merged_ids == ["720317081_2024-05-19_-5.75_bbb"]


def test_the_choice_ignores_the_order_of_the_input(db):
    """Task 8.2: the choice is stable, so two machines agree."""
    _row(db, "zzz", source_file="first.sta", source_line=1)
    _row(db, "aaa", source_file="second.mta", source_line=99)

    assert preview_merge(db).groups[0].survivor_id == "aaa"


def test_the_choice_ignores_the_source_file(db):
    _row(db, "aaa", source_file="zzz_last.mta")
    _row(db, "bbb", source_file="aaa_first.sta")

    assert preview_merge(db).groups[0].survivor_id == "aaa"


# ---------------------------------------------------------------------------
# 8.3 The refusal of a conflict
# ---------------------------------------------------------------------------


def test_two_different_manual_categories_refuse_the_group(db):
    """Task 8.3: only the snapshot import may replace a manual categorization."""
    _row(db, "aaa", manual_category="groceries")
    _row(db, "bbb", manual_category="restaurant")

    preview = preview_merge(db)

    assert preview.groups == []
    assert len(preview.refused) == 1
    assert preview.refused[0].manual_categories == ["groceries", "restaurant"]


def test_a_refused_group_changes_no_row(db):
    _row(db, "aaa", manual_category="groceries")
    _row(db, "bbb", manual_category="restaurant")

    merge_duplicates(db)

    for row_id in ("aaa", "bbb"):
        row = db.get(Transaction, row_id)
        assert row.deleted_at is None
        assert row.merged_into is None


def test_the_same_manual_category_merges(db):
    _row(db, "aaa", manual_category="groceries")
    _row(db, "bbb", manual_category="groceries")

    preview = merge_duplicates(db)

    assert len(preview.groups) == 1
    assert preview.refused == []
    assert db.get(Transaction, "bbb").merged_into == "aaa"


# ---------------------------------------------------------------------------
# 8.4 The carried manual categorization
# ---------------------------------------------------------------------------


def test_the_merge_carries_the_manual_category(db):
    """Task 8.4: no manual categorization goes away."""
    _row(db, "aaa")
    _row(db, "bbb", manual_category="groceries")

    merge_duplicates(db)

    assert db.get(Transaction, "aaa").manual_category == "groceries"


def test_the_merge_keeps_the_manual_category_of_the_survivor(db):
    _row(db, "aaa", manual_category="groceries")
    _row(db, "bbb")

    merge_duplicates(db)

    assert db.get(Transaction, "aaa").manual_category == "groceries"


def test_the_merge_carries_the_manual_tags(db):
    _row(db, "aaa")
    _row(db, "bbb", manual_tags="holiday")

    merge_duplicates(db)

    assert db.get(Transaction, "aaa").manual_tags == "holiday"


# ---------------------------------------------------------------------------
# 8.5 The flag and the merged_into column
# ---------------------------------------------------------------------------


def test_the_merge_flags_the_other_row(db):
    _row(db, "aaa")
    _row(db, "bbb")

    merge_duplicates(db)

    other = db.get(Transaction, "bbb")
    assert other.deleted_at is not None
    assert other.merged_into == "aaa"
    assert db.get(Transaction, "aaa").deleted_at is None


def test_the_merge_deletes_no_row(db):
    _row(db, "aaa")
    _row(db, "bbb")

    merge_duplicates(db)

    assert db.query(Transaction).count() == 2


def test_the_live_predicate_hides_the_merged_row(db):
    """Task 8.5: each total holds the survivor one time."""
    from abn_combined.core.filters import live_only

    _row(db, "aaa")
    _row(db, "bbb")
    merge_duplicates(db)

    live = live_only(db.query(Transaction)).all()

    assert [row.id for row in live] == ["aaa"]


# ---------------------------------------------------------------------------
# 8.6 The report
# ---------------------------------------------------------------------------


def test_the_merge_stores_a_report(db):
    _row(db, "aaa")
    _row(db, "bbb", manual_category="groceries")

    merge_duplicates(db)

    report = db.query(MergeReport).one()
    assert report.summary == {"groups": 1, "rows": 1, "refused": 0}
    assert report.groups[0]["survivor_id"] == "aaa"
    assert report.groups[0]["merged_ids"] == ["bbb"]
    assert report.groups[0]["carried_category"] == "groceries"


def test_the_report_names_a_refused_group(db):
    _row(db, "aaa", manual_category="groceries")
    _row(db, "bbb", manual_category="restaurant")

    merge_duplicates(db)

    report = db.query(MergeReport).one()
    assert report.summary["refused"] == 1
    assert report.refused[0]["row_ids"] == ["aaa", "bbb"]
    assert "manual categories" in report.refused[0]["reason"]


def test_no_report_without_a_group(db):
    _row(db, "aaa")

    merge_duplicates(db)

    assert db.query(MergeReport).count() == 0


# ---------------------------------------------------------------------------
# 8.7 The undo
# ---------------------------------------------------------------------------


def test_the_undo_brings_the_row_back(db):
    _row(db, "aaa")
    _row(db, "bbb")
    merge_duplicates(db)

    restored = undo_merge(db, "aaa")

    assert restored == ["bbb"]
    other = db.get(Transaction, "bbb")
    assert other.deleted_at is None
    assert other.merged_into is None


def test_the_undo_keeps_the_carried_manual_category(db):
    """Task 8.7: the user may have relied on the carried value since."""
    _row(db, "aaa")
    _row(db, "bbb", manual_category="groceries")
    merge_duplicates(db)

    undo_merge(db, "aaa")

    assert db.get(Transaction, "aaa").manual_category == "groceries"


def test_the_undo_reports_nothing_when_the_row_is_gone(db):
    """Task 8.7: the purge keeps a merged row, so this needs a hand flag first."""
    _row(db, "aaa")

    assert undo_merge(db, "aaa") == []


def test_the_live_predicate_shows_both_rows_after_the_undo(db):
    from abn_combined.core.filters import live_only

    _row(db, "aaa")
    _row(db, "bbb")
    merge_duplicates(db)
    undo_merge(db, "aaa")

    live = live_only(db.query(Transaction)).all()

    assert sorted(row.id for row in live) == ["aaa", "bbb"]


# ---------------------------------------------------------------------------
# The preview changes no row
# ---------------------------------------------------------------------------


def test_the_preview_changes_no_row(db):
    _row(db, "aaa")
    _row(db, "bbb")

    preview_merge(db)

    assert db.get(Transaction, "bbb").deleted_at is None
    assert db.get(Transaction, "bbb").merged_into is None
    assert db.query(MergeReport).count() == 0


def test_the_preview_counts_the_rows(db):
    _row(db, "aaa")
    _row(db, "bbb")
    _row(db, "ccc")

    preview = preview_merge(db)

    assert preview.row_count == 2
    assert preview.groups[0].merged_ids == ["bbb", "ccc"]


# ---------------------------------------------------------------------------
# The values and the pairs that the real statement holds
#
# `tests/fixtures/mt940_sample.STA` holds 2291 rows. Two findings from it drive
# the two groups of tests below.
# ---------------------------------------------------------------------------


def test_notprovided_makes_no_group(db):
    """The sample statement holds `NOTPROVIDED` 136 times.

    Without this exclusion the merge would fold 136 unrelated payments into
    one row.
    """
    _row(db, "aaa", reference="NOTPROVIDED")
    _row(db, "bbb", reference="NOTPROVIDED")
    _row(db, "ccc", reference="NOTPROVIDED")

    assert preview_merge(db).groups == []


def test_a_split_sentinel_makes_no_group(db):
    """An MT940 description wraps, so the sentinel also appears split.

    The sample statement holds `NOTP ROVIDED` three times.
    """
    _row(db, "aaa", reference="NOTP ROVIDED")
    _row(db, "bbb", reference="NOTPROVIDED")

    assert preview_merge(db).groups == []


def test_a_reversal_is_not_a_duplicate(db):
    """A reversal carries the reference of the payment that it reverses.

    The sample statement holds three such pairs. One is a direct debit of
    -149.88 with its `SEPA INCASSO TERUGBOEKING` of +149.88. Those are two
    transactions, and the merge must keep both.
    """
    _row(db, "aaa", amount=-149.88, description="SEPA INCASSO ALGEMEEN DOORLOPEND")
    _row(db, "bbb", amount=149.88, description="SEPA INCASSO TERUGBOEKING")

    assert preview_merge(db).groups == []


def test_the_two_forms_of_one_payment_still_merge(db):
    """The amount in the key does not break the case that the change targets.

    The two description forms of one payment report the same amount, because
    they describe one statement line.
    """
    _row(db, "aaa", amount=-5.75)
    _row(db, "bbb", amount=-5.75)

    assert len(preview_merge(db).groups) == 1


def test_the_real_statement_holds_no_duplicate_group(db):
    """The whole sample statement must yield no group.

    Each repeated reference in that file is either a sentinel or a reversal
    pair. A group here would mean the merge folds a row that it must keep.
    """
    import json as _json
    from datetime import date as _date

    from abn_combined.parsers import parse_mt940_file

    txns = parse_mt940_file("tests/fixtures/mt940_sample.STA")
    for index, trans in enumerate(txns):
        structured = trans.get("description_structured")
        db.add(
            Transaction(
                id=f"row-{index:05d}",
                accountNumber=str(trans.get("accountNumber") or ACCOUNT),
                transactiondate=trans.get("transactiondate") or _date(2024, 5, 19),
                amount=trans.get("amount") or 0,
                description=trans.get("description"),
                description_structured=structured,
                currency="EUR",
                end_to_end_reference=(
                    _json.loads(structured).get("end_to_end_reference")
                    if structured
                    else None
                ),
            )
        )
    db.commit()

    preview = preview_merge(db)

    assert preview.groups == [], (
        "the merge would fold a row of the real statement: "
        f"{[(g.reference, g.amount, g.merged_ids) for g in preview.groups[:5]]}"
    )
