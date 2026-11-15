"""The one-time rewrite of a stored SEPA structured description.

The rules read ``description_structured``, so a rename of a key in the parser
changes nothing for a row that the system already stored. The pass reparses
such a row. See task 4.5 of
openspec/changes/unify-sepa-description-and-reference-dedup.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from abn_combined.core.models import Base, Transaction
from abn_combined.core.restructure import (
    needs_rewrite,
    rewrite_sepa_structured_descriptions,
)

TAGGED = (
    "/TRTP/SEPA INCASSO ALGEMEEN DOORLOPEND/CSID/VP20XNL847867841319 "
    "/NAME/LEBARA/MARF/B0OXIVC5T2O3ZJ58/REMI/LEBARA NL-039442543-277 "
    "/IBAN/NL65ADYB0257164544/BIC/ADYBNL2A/EREF/KFF5Q4D85TQK39G6"
)
LABELLED = (
    "SEPA INCASSO ALGEMEEN DOORLOPEND INCASSANT: VP20XNL847867841319 "
    "NAAM: LEBARA MACHTIGING: B0OXIVC5T2O3ZJ58 "
    "OMSCHRIJVING: LEBARA NL-03944254 3-277 IBAN: NL65ADYB0257164544 "
    "KENMERK: KFF5Q4D85TQK39G6"
)
POS = (
    "BEA, BETAALPAS                   JUMBO 123375,PAS603 "
    "NR:97EX02, 30.05.24/17:07        DDUWAS EN KEE"
)

# The shape that the old tagged parser stored for the LEBARA direct debit.
OLD_TAGGED_STRUCTURED = {
    "transaction_type": "SEPA INCASSO ALGEMEEN DOORLOPEND",
    "other_fields": {
        "CSID": "VP20XNL847867841319",
        "MARF": "B0OXIVC5T2O3ZJ58",
    },
    "name": "LEBARA",
    "remittance_info": "LEBARA NL-039442543-277",
    "iban": "NL65ADYB0257164544",
    "bic": "ADYBNL2A",
    "end_to_end_reference": "KFF5Q4D85TQK39G6",
    "format": "mt940",
}

# The shape that the old labelled parser stored for the same payment.
OLD_LABELLED_STRUCTURED = {
    "sepa_type": "INCASSO",
    "transaction_type": "SEPA Direct Debit",
    "direct_debit_type": "General",
    "recurring": True,
    "iban": "NL65ADYB0257164544",
    "name": "LEBARA",
    "description": "LEBARA NL-03944254 3-277",
    "creditor_identifier": "VP20XNL847867841319",
    "mandate_reference": "B0OXIVC5T2O3ZJ58",
    "reference": "KFF5Q4D85TQK39G6",
    "format": "sepa",
}


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'restructure.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _add(db, row_id: str, description: str, structured: dict) -> Transaction:
    row = Transaction(
        id=row_id,
        accountNumber="720317081",
        transactiondate=date(2024, 5, 19),
        amount=-5.75,
        description=description,
        description_structured=json.dumps(structured, ensure_ascii=False),
        currency="EUR",
    )
    db.add(row)
    db.commit()
    return row


def _structured(db, row_id: str) -> dict:
    row = db.get(Transaction, row_id)
    return json.loads(row.description_structured)


# ---------------------------------------------------------------------------
# needs_rewrite
# ---------------------------------------------------------------------------


def test_needs_rewrite_selects_a_stored_tagged_row():
    """A tagged SEPA row held the format mt940 before the change."""
    assert needs_rewrite(OLD_TAGGED_STRUCTURED) is True


def test_needs_rewrite_selects_a_stored_labelled_row():
    """A labelled row held the two old key names."""
    assert needs_rewrite(OLD_LABELLED_STRUCTURED) is True


def test_needs_rewrite_skips_a_canonical_row():
    """The pass matches nothing after its first run."""
    from abn_combined.parsers.description import parse_transaction_description

    assert needs_rewrite(parse_transaction_description(TAGGED)) is False
    assert needs_rewrite(parse_transaction_description(LABELLED)) is False


def test_needs_rewrite_skips_a_pos_row():
    """A point-of-sale row names no SEPA payment."""
    from abn_combined.parsers.description import parse_transaction_description

    assert needs_rewrite(parse_transaction_description(POS)) is False


def test_needs_rewrite_skips_another_tagged_type():
    """A tagged IDEAL row keeps the format mt940, and it needs no rewrite."""
    assert needs_rewrite({"format": "mt940", "transaction_type": "IDEAL"}) is False


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------


def test_the_pass_rewrites_a_stored_tagged_row(db_session):
    """Task 4.5: the stored tagged row holds the canonical keys after the pass."""
    _add(db_session, "tagged", TAGGED, OLD_TAGGED_STRUCTURED)

    assert rewrite_sepa_structured_descriptions(db_session) == 1

    data = _structured(db_session, "tagged")
    assert data["creditor_identifier"] == "VP20XNL847867841319"
    assert data["mandate_reference"] == "B0OXIVC5T2O3ZJ58"
    assert data["format"] == "sepa"
    assert data["transaction_type"] == "SEPA Direct Debit"
    assert "other_fields" not in data


def test_the_pass_rewrites_a_stored_labelled_row(db_session):
    """Task 4.5: the two old key names go away."""
    _add(db_session, "labelled", LABELLED, OLD_LABELLED_STRUCTURED)

    assert rewrite_sepa_structured_descriptions(db_session) == 1

    data = _structured(db_session, "labelled")
    assert data["remittance_info"] == "LEBARA NL-03944254 3-277"
    assert data["end_to_end_reference"] == "KFF5Q4D85TQK39G6"
    assert "description" not in data
    assert "reference" not in data


def test_the_pass_leaves_a_pos_row(db_session):
    """Task 4.5: the pass does not change a point-of-sale row."""
    from abn_combined.parsers.description import parse_transaction_description

    before = parse_transaction_description(POS)
    _add(db_session, "pos", POS, before)

    assert rewrite_sepa_structured_descriptions(db_session) == 0
    assert _structured(db_session, "pos") == before


def test_the_pass_fills_the_reference_column(db_session):
    """The pass also fills the new column for a row that it rewrites."""
    _add(db_session, "tagged", TAGGED, OLD_TAGGED_STRUCTURED)

    rewrite_sepa_structured_descriptions(db_session)

    row = db_session.get(Transaction, "tagged")
    assert row.end_to_end_reference == "KFF5Q4D85TQK39G6"


def test_the_pass_is_idempotent(db_session):
    """A second run matches no row."""
    _add(db_session, "tagged", TAGGED, OLD_TAGGED_STRUCTURED)
    _add(db_session, "labelled", LABELLED, OLD_LABELLED_STRUCTURED)

    assert rewrite_sepa_structured_descriptions(db_session) == 2
    assert rewrite_sepa_structured_descriptions(db_session) == 0


def test_the_pass_keeps_a_manual_category(db_session):
    """The pass changes no categorization."""
    row = _add(db_session, "tagged", TAGGED, OLD_TAGGED_STRUCTURED)
    row.manual_category = "utilities"
    row.category = "utilities"
    db_session.commit()

    rewrite_sepa_structured_descriptions(db_session)

    row = db_session.get(Transaction, "tagged")
    assert row.manual_category == "utilities"


# ---------------------------------------------------------------------------
# The field target of a rule
#
# A rule names a structured key by its field target. An unknown field target
# matches nothing, so the rename of a key must carry each rule with it. See
# openspec/changes/unify-sepa-description-and-reference-dedup, group 6.
# ---------------------------------------------------------------------------


def _rule(db, **over):
    from abn_combined.core.models import CategorizationRule

    defaults = dict(
        priority=100,
        rule_type="structured_field",
        match_pattern="contains",
        field_target="reference",
        match_value="KFF5Q4D85TQK39G6",
        category="utilities",
        is_active=True,
    )
    defaults.update(over)
    rule = CategorizationRule(**defaults)
    db.add(rule)
    db.commit()
    return rule


def test_migration_renames_the_reference_target(db_session):
    """Task 6.1: the reference key takes its canonical name."""
    from abn_combined.core.restructure import migrate_rule_field_targets

    rule = _rule(db_session)

    migrate_rule_field_targets(db_session)

    db_session.refresh(rule)
    assert rule.field_target == "end_to_end_reference"


def test_migration_renames_a_structured_description_target(db_session):
    """Task 6.1: a structured-field rule on description takes the new name."""
    from abn_combined.core.restructure import migrate_rule_field_targets

    rule = _rule(db_session, field_target="description", rule_type="structured_field")

    migrate_rule_field_targets(db_session)

    db_session.refresh(rule)
    assert rule.field_target == "remittance_info"


def test_migration_leaves_a_full_description_rule(db_session):
    """Task 6.1: that target names the raw text, and not a structured key."""
    from abn_combined.core.restructure import migrate_rule_field_targets

    rule = _rule(
        db_session, field_target="description", rule_type="full_description"
    )

    migrate_rule_field_targets(db_session)

    db_session.refresh(rule)
    assert rule.field_target == "description"


def test_migration_leaves_a_keyword_rule_on_the_description(db_session):
    """Task 6.1: a keyword rule also reads the raw text."""
    from abn_combined.core.restructure import migrate_rule_field_targets

    rule = _rule(db_session, field_target="description", rule_type="keyword")

    migrate_rule_field_targets(db_session)

    db_session.refresh(rule)
    assert rule.field_target == "description"


def test_migration_renames_a_condition_reference(db_session):
    """Task 6.1: an extra condition takes the reference rename."""
    from abn_combined.core.models import RuleCondition
    from abn_combined.core.restructure import migrate_rule_field_targets

    rule = _rule(db_session, field_target="iban", rule_type="account_iban")
    condition = RuleCondition(
        rule_id=rule.id,
        field_target="reference",
        match_pattern="contains",
        match_value="KFF5",
        operator="AND",
        sort_order=0,
    )
    db_session.add(condition)
    db_session.commit()

    migrate_rule_field_targets(db_session)

    db_session.refresh(condition)
    assert condition.field_target == "end_to_end_reference"


def test_migration_leaves_a_condition_on_the_description(db_session):
    """Task 6.1: an extra condition on description reads the raw text.

    `_evaluate_single_condition` short-circuits that target to the raw text for
    each rule type. A rename there would change the behavior.
    """
    from abn_combined.core.models import RuleCondition
    from abn_combined.core.restructure import migrate_rule_field_targets

    rule = _rule(db_session, field_target="iban", rule_type="account_iban")
    condition = RuleCondition(
        rule_id=rule.id,
        field_target="description",
        match_pattern="contains",
        match_value="LEBARA",
        operator="AND",
        sort_order=0,
    )
    db_session.add(condition)
    db_session.commit()

    migrate_rule_field_targets(db_session)

    db_session.refresh(condition)
    assert condition.field_target == "description"


def test_migration_writes_a_report(db_session):
    """Task 6.2: the migration records the rule before and after the change."""
    from abn_combined.core.restructure import migrate_rule_field_targets

    _rule(db_session)

    report = migrate_rule_field_targets(db_session)

    assert report is not None
    assert report.action == "migrate_fields"
    assert report.rule_after["renamed"][0]["from"] == "reference"
    assert report.rule_after["renamed"][0]["to"] == "end_to_end_reference"
    assert report.rule_before["renamed"][0]["to"] == "reference"


def test_migration_writes_no_report_when_nothing_changes(db_session):
    """The migration is idempotent."""
    from abn_combined.core.restructure import migrate_rule_field_targets

    _rule(db_session)

    assert migrate_rule_field_targets(db_session) is not None
    assert migrate_rule_field_targets(db_session) is None


def test_migration_keeps_a_manual_category(db_session):
    """Task 6.3: the reapplication does not overwrite a manual categorization."""
    from abn_combined.core.restructure import migrate_rule_field_targets

    row = _add(db_session, "tagged", TAGGED, OLD_TAGGED_STRUCTURED)
    row.manual_category = "utilities"
    row.category = "groceries"
    db_session.commit()

    # A rule that would otherwise categorize the row as something else.
    _rule(db_session, category="telecom")

    migrate_rule_field_targets(db_session)

    row = db_session.get(Transaction, "tagged")
    assert row.manual_category == "utilities"
