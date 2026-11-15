"""The second match key: a duplicate that carries no end-to-end reference.

A transfer between two accounts of the user carries no reference. The bank
writes `NOTPROVIDED`, so the reference check cannot join the two description
forms of such a transfer.

Each fixture below models a shape that a real database of 7202 rows holds. See
openspec/changes/match-duplicates-without-a-reference.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from abn_combined.core.dedup import check_duplicates, counterparty_key
from abn_combined.core.merge import merge_duplicates, preview_merge
from abn_combined.core.models import Base, Transaction

ACCOUNT = "915190158"
SAVINGS_IBAN = "NL92ABNA8756430569"
PAYPAL_IBAN = "LU89563814393733142M"

# The two downloads that gave the two description forms.
FILE_A = "MT940251116145104.STA"
FILE_B = "MT940260105110307.STA"


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'counterparty.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _structured(iban: str, remittance: str | None, reference: str = "NOTPROVIDED"):
    data: dict[str, object] = {
        "format": "sepa",
        "sepa_type": "OVERBOEKING",
        "transaction_type": "SEPA Transfer",
        "iban": iban,
        "end_to_end_reference": reference,
    }
    if remittance is not None:
        data["remittance_info"] = remittance
    return json.dumps(data, ensure_ascii=False)


def _parsed(
    *,
    iban: str = SAVINGS_IBAN,
    remittance: str | None = None,
    reference: str = "NOTPROVIDED",
    amount: float = -1000.00,
    source_file: str = FILE_A,
    when: date = date(2025, 11, 10),
    description: str | None = None,
):
    # The raw description holds the remittance text, as a real statement does.
    # Without it two rows of one day and one amount share a transaction id, and
    # the older id check would hide what this key does.
    if description is None:
        description = f"SEPA OVERBOEKING {iban} {remittance or ''}".strip()
    return {
        "accountNumber": ACCOUNT,
        "transactiondate": when,
        "amount": amount,
        "description": description,
        "description_structured": _structured(iban, remittance, reference),
        "currency": "EUR",
        "source_file": source_file,
    }


def _add(db, row_id: str, **over) -> Transaction:
    trans = _parsed(**over)
    row = Transaction(
        id=row_id,
        accountNumber=trans["accountNumber"],
        transactiondate=trans["transactiondate"],
        amount=trans["amount"],
        description=trans["description"],
        description_structured=trans["description_structured"],
        currency="EUR",
        source_file=trans["source_file"],
    )
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------------------
# 1. The key itself
# ---------------------------------------------------------------------------


def test_the_key_normalizes_the_remittance_text():
    """Task 1.1: the wrap of the description splits the remittance text."""
    a = counterparty_key(_parsed(remittance="JYNQ VAN LCJFOST"))
    b = counterparty_key(_parsed(remittance="JYNQ VAN LCJFO ST"))
    assert a == b


def test_the_key_is_absent_with_a_usable_reference():
    """Task 1.2: the reference key already covers such a row."""
    assert counterparty_key(_parsed(reference="KFF5Q4D85TQK39G6")) is None


def test_the_key_is_absent_without_an_iban():
    """Task 1.2: a point-of-sale row holds no counterparty IBAN."""
    trans = _parsed()
    trans["description_structured"] = json.dumps(
        {"format": "pos", "merchant_name": "JUMBO"}
    )
    assert counterparty_key(trans) is None


def test_the_key_holds_the_amount_and_the_date():
    """Task 1.2: the key separates two transfers of two days."""
    a = counterparty_key(_parsed(when=date(2025, 11, 10)))
    b = counterparty_key(_parsed(when=date(2025, 11, 11)))
    c = counterparty_key(_parsed(amount=-1500.00))
    assert a != b
    assert a != c


# ---------------------------------------------------------------------------
# 1.3 to 1.5 The duplicate check
# ---------------------------------------------------------------------------


def test_the_second_form_of_a_transfer_is_a_duplicate(db):
    """Task 1.3: the case that the whole change targets."""
    from abn_combined.core.dedup import insert_transactions

    insert_transactions(db, [_parsed(source_file=FILE_A)])

    new, dup = check_duplicates(db, [_parsed(source_file=FILE_B)])

    assert new == []
    assert len(dup) == 1


def test_three_payments_of_one_day_all_import(db):
    """Task 1.4: only the remittance text tells them apart.

    The real database holds three payments of -149,00 euro of one day to one
    PayPal IBAN. A key without the remittance text folds two of them away.
    """
    batch = [
        _parsed(
            iban=PAYPAL_IBAN,
            amount=-149.00,
            remittance=text,
            when=date(2025, 4, 29),
            source_file=FILE_A,
        )
        for text in (
            "1881164974955/PAYP AL",
            "3404065959685/PAYP AL",
            "7624611028858/PAYP AL",
        )
    ]

    new, dup = check_duplicates(db, batch)

    assert len(new) == 3
    assert dup == []


def test_a_row_with_a_reference_uses_the_reference_key_only(db):
    """Task 1.5: one row never matches two keys."""
    from abn_combined.core.dedup import insert_transactions

    insert_transactions(db, [_parsed(reference="REALREF12345", source_file=FILE_A)])

    # The same payment in the other form, with the same reference.
    new, dup = check_duplicates(
        db, [_parsed(reference="REALREF12345", source_file=FILE_B)]
    )
    assert new == []
    assert len(dup) == 1


# ---------------------------------------------------------------------------
# 2. The rule of the statement file
# ---------------------------------------------------------------------------


def test_two_rows_of_one_file_are_two_payments(db):
    """Task 2.1: one file never reports one payment twice in two forms."""
    batch = [
        _parsed(source_file=FILE_A, description="first"),
        _parsed(source_file=FILE_A, description="second"),
    ]

    new, dup = check_duplicates(db, batch)

    assert len(new) == 2
    assert dup == []


def test_two_rows_of_two_files_are_one_payment(db):
    """Task 2.2."""
    batch = [
        _parsed(source_file=FILE_A, description="the tagged form"),
        _parsed(source_file=FILE_B, description="the labelled form"),
    ]

    new, dup = check_duplicates(db, batch)

    assert len(new) == 1
    assert len(dup) == 1


# ---------------------------------------------------------------------------
# 3. The merge
# ---------------------------------------------------------------------------


def test_the_merge_finds_a_transfer_pair(db):
    """Task 3.1 and 4.2: 189 of the 214 real groups hold no remittance text."""
    _add(db, "aaa", source_file=FILE_A)
    _add(db, "bbb", source_file=FILE_B)

    preview = preview_merge(db)

    assert len(preview.groups) == 1
    assert preview.groups[0].matched_by == "counterparty"
    assert preview.groups[0].survivor_id == "aaa"
    assert preview.refused == []


def test_the_merge_refuses_a_cluster_of_one_file(db):
    """Task 3.2: the PayPal cluster of the real database."""
    for index, text in enumerate(
        ("1881164974955/PAYPAL", "3404065959685/PAYPAL", "7624611028858/PAYPAL")
    ):
        _add(
            db,
            f"pp{index}",
            iban=PAYPAL_IBAN,
            amount=-149.00,
            remittance=text,
            when=date(2025, 4, 29),
            source_file=FILE_A,
        )

    preview = preview_merge(db)

    # Three different remittance texts make three groups of one row each.
    assert preview.groups == []
    assert preview.refused == []


def test_the_merge_refuses_two_equal_payments_of_one_file(db):
    """Task 3.2: one file gives two rows of the group."""
    _add(db, "aaa", source_file=FILE_A)
    _add(db, "bbb", source_file=FILE_A)

    preview = preview_merge(db)

    assert preview.groups == []
    assert len(preview.refused) == 1
    assert preview.refused[0].matched_by == "counterparty"
    assert "one statement file" in preview.refused[0].reason


def test_a_refused_cluster_changes_no_row(db):
    """Task 3.2: the merge must not fold a genuine repeated payment."""
    _add(db, "aaa", source_file=FILE_A)
    _add(db, "bbb", source_file=FILE_A)

    merge_duplicates(db)

    for row_id in ("aaa", "bbb"):
        row = db.get(Transaction, row_id)
        assert row.deleted_at is None
        assert row.merged_into is None


def test_the_four_row_cluster_refuses(db):
    """Task 4.1: two payments that two downloads each report.

    The real database holds two such clusters. Each one holds two rows of each
    of two files, so each file gives more than one row of the group.
    """
    for index, source in enumerate((FILE_A, FILE_A, FILE_B, FILE_B)):
        _add(db, f"row{index}", source_file=source, when=date(2026, 9, 7), amount=-530.00)

    preview = preview_merge(db)

    assert preview.groups == []
    assert len(preview.refused) == 1


def test_the_group_names_the_counterparty(db):
    """Task 3.3: the report names the key that found the group."""
    _add(db, "aaa", remittance="BIQTVW BIRTHDAY", source_file=FILE_A)
    _add(db, "bbb", remittance="BIQTVW BIRTHDAY", source_file=FILE_B)

    group = preview_merge(db).groups[0]

    assert group.matched_by == "counterparty"
    assert SAVINGS_IBAN in group.reference
    assert "BIQTVW BIRTHDAY" in group.reference


def test_a_reference_group_still_names_the_reference(db):
    """Task 3.3: the other kind of group keeps its own label."""
    _add(db, "aaa", reference="KFF5Q4D85TQK39G6", source_file=FILE_A)
    _add(db, "bbb", reference="KFF5Q4D85TQK39G6", source_file=FILE_B)

    group = preview_merge(db).groups[0]

    assert group.matched_by == "reference"
    assert group.reference == "KFF5Q4D85TQK39G6"


def test_a_row_belongs_to_one_group_only(db):
    """Task 3.5: the reference key wins, so no row is counted twice."""
    _add(db, "aaa", reference="KFF5Q4D85TQK39G6", source_file=FILE_A)
    _add(db, "bbb", reference="KFF5Q4D85TQK39G6", source_file=FILE_B)
    _add(db, "ccc", source_file=FILE_A)
    _add(db, "ddd", source_file=FILE_B)

    preview = preview_merge(db)

    assert len(preview.groups) == 2
    folded = [rid for g in preview.groups for rid in g.merged_ids]
    assert sorted(folded) == ["bbb", "ddd"]
    assert len(set(folded)) == len(folded)


# ---------------------------------------------------------------------------
# The date belongs to the group key
#
# The first implementation of the discovery dropped the date from the group
# key. Each monthly transfer of one amount to one account then joined one
# group. On a real database that produced a group of 21 rows that spanned two
# years. These tests hold the date in the key.
# ---------------------------------------------------------------------------


def test_the_group_key_holds_the_date(db):
    """Two transfers of two days are two payments, not one group."""
    _add(db, "jan", when=date(2026, 1, 20), source_file=FILE_A)
    _add(db, "feb", when=date(2026, 2, 20), source_file=FILE_B)

    preview = preview_merge(db)

    assert preview.groups == []
    assert preview.refused == []


def test_a_monthly_transfer_makes_no_group(db):
    """The real shape that the bug produced: one amount, one IBAN, many dates."""
    for month in range(1, 13):
        _add(
            db,
            f"m{month:02d}",
            when=date(2026, month, 20),
            amount=-200.00,
            source_file=f"download{month:02d}.STA",
        )

    preview = preview_merge(db)

    assert preview.groups == [], (
        "a monthly transfer must not form a group: "
        f"{[(g.reference, g.merged_ids) for g in preview.groups]}"
    )
    assert preview.refused == []


def test_every_row_of_a_group_holds_one_date(db):
    """No group may ever span two dates."""
    _add(db, "a1", when=date(2026, 1, 20), source_file=FILE_A)
    _add(db, "a2", when=date(2026, 1, 20), source_file=FILE_B)
    _add(db, "b1", when=date(2026, 2, 20), source_file=FILE_A)
    _add(db, "b2", when=date(2026, 2, 20), source_file=FILE_B)

    preview = preview_merge(db)

    assert len(preview.groups) == 2
    for group in preview.groups:
        dates = {
            db.get(Transaction, rid).transactiondate
            for rid in [group.survivor_id, *group.merged_ids]
        }
        assert len(dates) == 1, f"the group spans {dates}"
