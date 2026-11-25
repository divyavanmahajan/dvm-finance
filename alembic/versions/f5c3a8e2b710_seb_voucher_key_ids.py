"""change each stored SEB id to the SEB voucher key

Revision ID: f5c3a8e2b710
Revises: e4b7d2a91c36
Create Date: 2026-11-25 00:00:00.000000

SEB gives one voucher number to many card payments. The old id
``<account>_<voucher>`` therefore joined different transactions. The new id
holds the voucher number, the booking date, the krona amount, and the krona
balance: ``<account>_<voucher>_<YYYY-MM-DD>_<amount>_<balance>``.

The upgrade takes the values from ``description_structured`` and
``transactiondate``. It changes ``transactions.id``,
``transactions.merged_into``, and ``rule_change_items.transaction_id`` in one
transaction. A row without ``voucher_number`` or ``native_amount`` keeps its id,
and the migration logs it. Before the upgrade changes a row, it copies the
database file to ``abn_combined.db.before-seb-ids-<timestamp>``.

The downgrade changes each id back to ``<account>_<voucher>``. It refuses when
two rows share one voucher number, because the old form cannot hold them.
"""
import json
import logging
import sqlite3
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f5c3a8e2b710'
down_revision: Union[str, None] = 'e4b7d2a91c36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


# A copy of core/dedup.py:format_krona and seb_voucher_key. A migration must
# not import application code that can change later.
def _krona(value) -> str:
    if value is None or value == "":
        return ""
    exact = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(exact, "f")


def _new_id(account, voucher, booking_date, amount, balance) -> str:
    return "_".join((account, voucher, str(booking_date)[:10], _krona(amount), _krona(balance)))


def _structured(text):
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _seb_rows(bind):
    return bind.execute(sa.text(
        "SELECT id, accountNumber, transactiondate, description_structured "
        "FROM transactions WHERE accountNumber LIKE 'seb:%'"
    )).fetchall()


def _backup(bind) -> None:
    """Copy the database file before the first change, with the SQLite backup API."""
    database = bind.engine.url.database
    if not database or database == ":memory:":
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = Path(database).with_name(f"{Path(database).name}.before-seb-ids-{stamp}")
    source = bind.connection.dbapi_connection
    copy = sqlite3.connect(str(target))
    try:
        source.backup(copy)
    finally:
        copy.close()
    logger.info("Copied the database to %s before the change of the SEB ids", target)


def _rename(bind, mapping: dict[str, str]) -> None:
    for old, new in mapping.items():
        params = {"old": old, "new": new}
        bind.execute(sa.text("UPDATE transactions SET id = :new WHERE id = :old"), params)
        bind.execute(
            sa.text("UPDATE transactions SET merged_into = :new WHERE merged_into = :old"), params
        )
        bind.execute(
            sa.text(
                "UPDATE rule_change_items SET transaction_id = :new WHERE transaction_id = :old"
            ),
            params,
        )


def upgrade() -> None:
    bind = op.get_bind()
    mapping: dict[str, str] = {}
    for trans_id, account, booking_date, structured_text in _seb_rows(bind):
        data = _structured(structured_text)
        voucher = data.get("voucher_number")
        if not voucher or trans_id != f"{account}_{voucher}":
            continue
        if data.get("native_amount") is None:
            logger.warning("The SEB row %s has no native_amount. It keeps its id.", trans_id)
            continue
        mapping[trans_id] = _new_id(
            account, str(voucher), booking_date, data["native_amount"], data.get("native_balance")
        )
    if not mapping:
        return
    _backup(bind)
    _rename(bind, mapping)
    logger.info("Changed the id of %d SEB rows to the SEB voucher key", len(mapping))


def downgrade() -> None:
    bind = op.get_bind()
    mapping: dict[str, str] = {}
    by_old: dict[str, list[str]] = {}
    for trans_id, account, booking_date, structured_text in _seb_rows(bind):
        data = _structured(structured_text)
        voucher = data.get("voucher_number")
        if not voucher or data.get("native_amount") is None:
            continue
        key = _new_id(
            account, str(voucher), booking_date, data["native_amount"], data.get("native_balance")
        )
        if trans_id != key:
            continue
        old = f"{account}_{voucher}"
        mapping[trans_id] = old
        by_old.setdefault(old, []).append(trans_id)
    shared = sorted(old for old, ids in by_old.items() if len(ids) > 1)
    if shared:
        raise RuntimeError(
            "Cannot downgrade: more than one SEB row has the voucher number of "
            f"{', '.join(shared)}. The old id form cannot hold them. "
            "Restore the backup abn_combined.db.before-seb-ids-<timestamp> instead."
        )
    _rename(bind, mapping)
