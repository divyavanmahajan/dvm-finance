"""Deterministic id generation and duplicate handling tests."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from abn_combined.constants import CASH_ACCOUNT
from abn_combined.core.dedup import (
    ReservedAccountError,
    check_duplicates,
    generate_transaction_id,
    insert_transactions,
)
from abn_combined.core.manual_txn import (
    create_manual_transaction,
    flag_manual_transaction,
)
from abn_combined.core.models import Base, Transaction


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _txn(**over):
    base = {
        "accountNumber": "720317081",
        "transactiondate": date(2024, 1, 1),
        "amount": -5.75,
        "description": "BEA test shop",
        "currency": "EUR",
    }
    base.update(over)
    return base


def test_id_is_deterministic():
    assert generate_transaction_id(_txn()) == generate_transaction_id(_txn())


def test_id_changes_with_amount():
    assert generate_transaction_id(_txn()) != generate_transaction_id(_txn(amount=-6.00))


def test_id_changes_with_description():
    a = generate_transaction_id(_txn())
    b = generate_transaction_id(_txn(description="OTHER"))
    assert a != b


def test_paypal_id_recipe():
    tid = generate_transaction_id(_txn(accountNumber="pp:me", paypal_transaction_id="ABC123"))
    assert tid == "pp:me_ABC123"


def test_wise_and_seb_id_recipe():
    assert generate_transaction_id(_txn(wise_transaction_id="W1")).endswith("_W1")
    assert generate_transaction_id(_txn(seb_voucher_id="V9")).endswith("_V9")


def test_insert_and_dedup_counting(session):
    txns = [_txn(), _txn(amount=-10.0, description="second")]
    new, dup = check_duplicates(session, txns)
    assert len(new) == 2
    assert len(dup) == 0

    insert_transactions(session, new)
    assert session.query(Transaction).count() == 2

    # Re-importing the same batch reports all duplicates, inserts nothing new.
    new2, dup2 = check_duplicates(session, txns)
    assert len(new2) == 0
    assert len(dup2) == 2


def test_in_batch_duplicates_counted(session):
    txns = [_txn(), _txn()]  # identical -> same id
    new, dup = check_duplicates(session, txns)
    assert len(new) == 1
    assert len(dup) == 1


def test_transaction_hash_written(session):
    insert_transactions(session, [_txn()])
    row = session.query(Transaction).one()
    assert row.transaction_hash and len(row.transaction_hash) == 64


# ---------------------------------------------------------------------------
# Hand-entered transactions and the duplicate check
# ---------------------------------------------------------------------------


def test_two_hand_entered_rows_with_the_same_values_both_exist(session):
    first = create_manual_transaction(
        session,
        transactiondate=date(2024, 1, 1),
        amount=-5.75,
        description="Cash at the market",
    )
    second = create_manual_transaction(
        session,
        transactiondate=date(2024, 1, 1),
        amount=-5.75,
        description="Cash at the market",
    )
    assert first.id != second.id
    assert session.query(Transaction).count() == 2


def test_an_import_never_matches_a_hand_entered_row(session):
    manual = create_manual_transaction(
        session,
        transactiondate=date(2024, 1, 1),
        amount=-5.75,
        description="BEA test shop",
    )
    # The statement reports the same payment for a real bank account.
    new, duplicates = check_duplicates(session, [_txn()])
    assert len(new) == 1
    assert duplicates == []

    insert_transactions(session, new)
    ids = {row.id for row in session.query(Transaction).all()}
    assert manual.id in ids
    assert len(ids) == 2


def test_the_id_of_a_flagged_row_stays_taken(session):
    manual = create_manual_transaction(
        session,
        transactiondate=date(2024, 1, 1),
        amount=-5.75,
        description="Cash at the market",
    )
    flag_manual_transaction(session, manual.id)
    existing_ids = {row[0] for row in session.query(Transaction.id).all()}
    assert manual.id in existing_ids


def test_insert_refuses_the_reserved_account(session):
    with pytest.raises(ReservedAccountError):
        insert_transactions(session, [_txn(accountNumber=CASH_ACCOUNT)])
    assert session.query(Transaction).count() == 0


# ---------------------------------------------------------------------------
# Duplicate detection by the end-to-end reference
#
# The bank writes one SEPA payment in two description forms. The two forms hold
# a different raw text, so the id of the two forms differs. Only the reference
# joins them. See
# openspec/changes/unify-sepa-description-and-reference-dedup, group 5.
# ---------------------------------------------------------------------------

import json  # noqa: E402

from abn_combined.core.dedup import (  # noqa: E402
    extract_end_to_end_reference,
    normalize_reference,
)
from abn_combined.parsers.description import (  # noqa: E402
    parse_transaction_description,
)

TAGGED_DESCRIPTION = (
    "/TRTP/SEPA INCASSO ALGEMEEN DOORLOPEND/CSID/VP20XNL847867841319 "
    "/NAME/LEBARA/MARF/B0OXIVC5T2O3ZJ58/REMI/LEBARA NL-039442543-277 "
    "/IBAN/NL65ADYB0257164544/BIC/ADYBNL2A/EREF/KFF5Q4D85TQK39G6"
)
LABELLED_DESCRIPTION = (
    "SEPA INCASSO ALGEMEEN DOORLOPEND INCASSANT: VP20XNL847867841319 "
    "NAAM: LEBARA MACHTIGING: B0OXIVC5T2O3ZJ58 "
    "OMSCHRIJVING: LEBARA NL-03944254 3-277 IBAN: NL65ADYB0257164544 "
    "KENMERK: KFF5Q4D85TQK39G6"
)
POS_DESCRIPTION = (
    "BEA, BETAALPAS                   JUMBO 123375,PAS603 "
    "NR:97EX02, 30.05.24/17:07        DDUWAS EN KEE"
)


def _parsed(description: str, **over):
    """Build a parsed transaction the way a parser hands one to the importer."""
    structured = parse_transaction_description(description)
    trans = _txn(description=description)
    if structured:
        trans["description_structured"] = json.dumps(structured, ensure_ascii=False)
    trans.update(over)
    return trans


# --- 5.1 the stored column -------------------------------------------------


def test_insert_stores_the_reference(session):
    """Task 5.1: a SEPA row holds its reference in the new column."""
    insert_transactions(session, [_parsed(TAGGED_DESCRIPTION)])

    row = session.query(Transaction).one()
    assert row.end_to_end_reference == "KFF5Q4D85TQK39G6"


def test_insert_leaves_a_pos_row_without_a_reference(session):
    """Task 5.1: a point-of-sale row holds an empty value."""
    insert_transactions(session, [_parsed(POS_DESCRIPTION)])

    row = session.query(Transaction).one()
    assert row.end_to_end_reference is None


# --- 5.2 the match ---------------------------------------------------------


def test_the_two_forms_have_different_ids():
    """The premise of the whole change: the id cannot join the two forms."""
    tagged = _parsed(TAGGED_DESCRIPTION)
    labelled = _parsed(LABELLED_DESCRIPTION)
    assert generate_transaction_id(tagged) != generate_transaction_id(labelled)


def test_the_labelled_form_matches_a_stored_tagged_row(session):
    """Task 5.2: the second description form counts as a duplicate."""
    insert_transactions(session, [_parsed(TAGGED_DESCRIPTION)])

    new, dup = check_duplicates(session, [_parsed(LABELLED_DESCRIPTION)])

    assert new == []
    assert len(dup) == 1
    assert session.query(Transaction).count() == 1


def test_the_two_forms_in_one_batch(session):
    """Task 5.2: the check also matches inside one batch."""
    new, dup = check_duplicates(
        session, [_parsed(TAGGED_DESCRIPTION), _parsed(LABELLED_DESCRIPTION)]
    )

    assert len(new) == 1
    assert len(dup) == 1


def test_two_accounts_keep_the_same_reference(session):
    """Task 5.2: the key holds the account, so two accounts do not collide."""
    insert_transactions(session, [_parsed(TAGGED_DESCRIPTION)])

    other = _parsed(LABELLED_DESCRIPTION, accountNumber="123456789")
    new, dup = check_duplicates(session, [other])

    assert len(new) == 1
    assert dup == []


# --- 5.3 the references that the check ignores -----------------------------


def test_nonref_does_not_join_two_payments(session):
    """Task 5.3: the bank writes NONREF when a payment carries no reference."""
    first = _parsed(
        "/TRTP/SEPA OVERBOEKING/IBAN/NL65ADYB0257164544/NAME/A/REMI/one"
        "/EREF/NONREF"
    )
    second = _parsed(
        "/TRTP/SEPA OVERBOEKING/IBAN/NL65ADYB0257164544/NAME/B/REMI/two"
        "/EREF/NONREF",
        amount=-9.99,
    )

    new, dup = check_duplicates(session, [first, second])

    assert len(new) == 2
    assert dup == []

    insert_transactions(session, new)
    assert session.query(Transaction).count() == 2
    assert {row.end_to_end_reference for row in session.query(Transaction)} == {None}


def test_the_helper_ignores_an_empty_reference():
    """Task 5.3: an empty value names no payment."""
    assert extract_end_to_end_reference({"end_to_end_reference": "   "}) is None
    assert extract_end_to_end_reference({}) is None


def test_two_pos_rows_stay_separate(session):
    """Task 5.3: a row with no reference falls back to the id only."""
    first = _parsed(POS_DESCRIPTION)
    second = _parsed(POS_DESCRIPTION, amount=-12.50)

    new, dup = check_duplicates(session, [first, second])

    assert len(new) == 2
    assert dup == []


# --- 5.4 the id does not change -------------------------------------------


def test_the_id_recipe_did_not_change():
    """Task 5.4: each already imported row keeps its id.

    The id must not come from the reference. A new id would make the next
    import write a second row, and the manual categorization of the first row
    would lose its transaction.
    """
    import hashlib

    for description in (TAGGED_DESCRIPTION, POS_DESCRIPTION):
        trans = _parsed(description)
        expected_hash = hashlib.md5(description.encode("utf-8")).hexdigest()[:16]
        assert (
            generate_transaction_id(trans)
            == f"720317081_2024-01-01_-5.75_{expected_hash}"
        )


def test_the_id_ignores_the_reference():
    """Task 5.4: the reference is a match key, and not part of the id."""
    without = _txn(description=TAGGED_DESCRIPTION)
    with_reference = _txn(
        description=TAGGED_DESCRIPTION, end_to_end_reference="KFF5Q4D85TQK39G6"
    )
    assert generate_transaction_id(without) == generate_transaction_id(with_reference)


# ---------------------------------------------------------------------------
# The real statement: the sentinel values and the reversal pairs
# ---------------------------------------------------------------------------


def test_notprovided_does_not_join_two_payments(session):
    """`tests/fixtures/mt940_sample.STA` holds `NOTPROVIDED` 136 times."""
    first = _parsed(
        "/TRTP/SEPA OVERBOEKING/IBAN/NL70ABNA0053384511/NAME/A/REMI/one"
        "/EREF/NOTPROVIDED"
    )
    second = _parsed(
        "/TRTP/SEPA OVERBOEKING/IBAN/NL70ABNA0053384511/NAME/B/REMI/two"
        "/EREF/NOTPROVIDED",
        amount=-19.50,
    )

    new, dup = check_duplicates(session, [first, second])

    assert len(new) == 2
    assert dup == []


def test_the_helper_ignores_a_split_sentinel():
    """An MT940 description wraps, so the sentinel also appears split."""
    assert extract_end_to_end_reference({"end_to_end_reference": "NOTP ROVIDED"}) is None
    assert extract_end_to_end_reference({"end_to_end_reference": "NON REF"}) is None


def test_a_reversal_is_not_a_duplicate(session):
    """A reversal carries the reference of the payment that it reverses.

    The amount belongs to the match key for this reason. The sample statement
    holds three such pairs.
    """
    debit = _parsed(
        "SEPA INCASSO ALGEMEEN DOORLOPEND INCASSANT: FT27DMW885132934094 "
        "NAAM: A MACHTIGING: M1 IBAN: NL65ADYB0257164544 "
        "KENMERK: RTPSAXQZ64FRLJY2",
        amount=-149.88,
    )
    reversal = _parsed(
        "SEPA INCASSO TERUGBOEKING        INCASSANT: FT27DMW885132934094 "
        "NAAM: A MACHTIGING: M1 IBAN: NL65ADYB0257164544 "
        "KENMERK: RTPSAXQZ64FRLJY2",
        amount=149.88,
    )

    new, dup = check_duplicates(session, [debit, reversal])

    assert len(new) == 2, "the merge must keep the payment and its reversal"
    assert dup == []


def test_the_two_forms_still_match_with_the_amount_in_the_key(session):
    """The amount does not break the case that the change targets.

    The two description forms of one payment report the same amount, because
    they describe one statement line.
    """
    insert_transactions(session, [_parsed(TAGGED_DESCRIPTION)])

    new, dup = check_duplicates(session, [_parsed(LABELLED_DESCRIPTION)])

    assert new == []
    assert len(dup) == 1


def test_the_reference_check_rejects_no_row_of_the_real_statement(session):
    """The reference check must add no duplicate on the sample statement.

    Each repeated reference in `tests/fixtures/mt940_sample.STA` is either a
    sentinel value or a reversal pair, so the reference check must reject none
    of its 2291 rows.

    The file does hold 19 duplicates of the id, from rows that share an
    account, a date, an amount and a description. That count is the behavior of
    the hash of the description, and it is older than the reference check. The
    test therefore compares the two checks instead of asserting a total.
    """
    from abn_combined.parsers import parse_mt940_file

    txns = parse_mt940_file("tests/fixtures/mt940_sample.STA")

    # The duplicates that the id alone reports.
    seen_ids: set[str] = set()
    id_only_duplicates = 0
    for trans in txns:
        trans_id = generate_transaction_id(trans)
        if trans_id in seen_ids:
            id_only_duplicates += 1
        else:
            seen_ids.add(trans_id)

    # The duplicates that the whole check reports.
    new, dup = check_duplicates(session, txns)

    added_by_the_reference = len(dup) - id_only_duplicates
    assert added_by_the_reference == 0, (
        "the reference check rejected a row of the real statement: "
        f"{[(t.get('amount'), (t.get('description') or '')[:50]) for t in dup[:5]]}"
    )
    assert len(new) + len(dup) == len(txns)


# ---------------------------------------------------------------------------
# The separators of one reference
#
# The bank prints one reference with different separators in the two
# description forms. An MT940 description also wraps at a fixed width, and the
# wrap can fall inside the reference. Each pair below comes from a real
# database of 7202 rows, where the user downloaded a long date range again and
# the bank answered with the other description form.
# ---------------------------------------------------------------------------


def test_normalize_reference_removes_each_separator():
    """The comparison form of a reference holds no separator."""
    assert normalize_reference("04-06-2026 21:42 737082 4431202372") == (
        "0406202621:427370824431202372"
    )
    assert normalize_reference("8022.7644 .9692.6345") == "8022764496926345"
    assert normalize_reference("notprovided") == "NOTPROVIDED"


def test_the_wrap_inside_a_reference_still_matches(session):
    """A wrapped reference and a whole reference name one payment."""
    first = _parsed(
        "/TRTP/IDEAL/WERO/IBAN/NL04ADYB8191761151/BIC/ADYBNL2A/NAME/WISE"
        "/REMI/one/EREF/30-05-2026 13:49 7180855028127978",
        amount=-1382.38,
    )
    second = _parsed(
        "SEPA IDEAL/WERO IBAN: NL04ADYB8191761151 BIC: ADYBNL2A "
        "NAAM: WISE OMSCHRIJVING: one "
        "KENMERK: 30-05-2026 13:49 718085 5028127978",
        amount=-1382.38,
    )

    new, dup = check_duplicates(session, [first, second])

    assert len(new) == 1
    assert len(dup) == 1


def test_different_separators_still_match(session):
    """One reference, printed with periods in the other form."""
    first = _parsed(
        "/TRTP/SEPA INCASSO ALGEMEEN DOORLOPEND/CSID/NL14ZZZ331428790000 "
        "/NAME/USKYROP VERZEKERINGEN/MARF/M1/REMI/one"
        "/EREF/8022764496926345",
        amount=-195.19,
    )
    second = _parsed(
        "SEPA INCASSO ALGEMEEN DOORLOPEND INCASSANT: NL14ZZZ331428790000 "
        "NAAM: USKYROP VERZEKERINGEN MACHTIGING: M1 OMSCHRIJVING: one "
        "KENMERK: 8022.7644 .9692.6345",
        amount=-195.19,
    )

    new, dup = check_duplicates(session, [first, second])

    assert len(new) == 1
    assert len(dup) == 1


def test_the_stored_row_keeps_the_original_reference(session):
    """The column holds what the bank wrote, and the comparison normalizes."""
    insert_transactions(
        session,
        [
            _parsed(
                "/TRTP/SEPA INCASSO ALGEMEEN DOORLOPEND/CSID/NL14ZZZ331428790000 "
                "/NAME/A/MARF/M1/REMI/one/EREF/8022.7644 .9692.6345",
                amount=-195.19,
            )
        ],
    )

    row = session.query(Transaction).one()
    assert row.end_to_end_reference == "8022.7644 .9692.6345"

    # The other form still matches it against the stored value.
    other = _parsed(
        "SEPA INCASSO ALGEMEEN DOORLOPEND INCASSANT: NL14ZZZ331428790000 "
        "NAAM: A MACHTIGING: M1 OMSCHRIJVING: one "
        "KENMERK: 8022764496926345",
        amount=-195.19,
    )
    new, dup = check_duplicates(session, [other])
    assert new == []
    assert len(dup) == 1


def test_a_split_sentinel_is_still_a_sentinel(session):
    """The real database holds `NOTPROVIDE D` and `NOTPROV IDED`."""
    for value in ("NOTPROVIDE D", "NOTPROV IDED", "NOT-PROVIDED"):
        assert (
            extract_end_to_end_reference({"end_to_end_reference": value}) is None
        ), value


def test_the_normalization_keeps_a_reversal_apart(session):
    """The amount still separates a payment from its reversal."""
    debit = _parsed(
        "/TRTP/SEPA INCASSO ALGEMEEN DOORLOPEND/CSID/C1/NAME/A/MARF/M1"
        "/REMI/one/EREF/BAE3765 3137668063490036 388846723",
        amount=-65.13,
    )
    reversal = _parsed(
        "/TRTP/SEPA INCASSO TERUGBOEKING/CSID/C1/NAME/A/MARF/M1"
        "/REMI/one/EREF/BAE37653137668063490036 388846723",
        amount=65.13,
    )

    new, dup = check_duplicates(session, [debit, reversal])

    assert len(new) == 2
    assert dup == []
