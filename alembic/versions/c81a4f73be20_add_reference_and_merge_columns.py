"""add end_to_end_reference and merged_into to transactions

Revision ID: c81a4f73be20
Revises: b3c1f0a27d44
Create Date: 2026-10-28 00:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c81a4f73be20'
down_revision: Union[str, None] = 'b3c1f0a27d44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The old key of the labelled parser, and the canonical key. A row from before
# this change holds either one.
_REFERENCE_KEYS = ('end_to_end_reference', 'reference')

# A reference that names no single payment. The column means "a usable
# reference" on each write path, so the backfill stores none of these. The
# values repeat the set in `core/dedup.py`; the migration must not import the
# application code, because that code moves on and the migration must not.
_UNUSABLE_REFERENCES = frozenset({'NONREF', 'NOTPROVIDED'})


def upgrade() -> None:
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('end_to_end_reference', sa.String(), nullable=True)
        )
        batch_op.add_column(sa.Column('merged_into', sa.String(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_transactions_end_to_end_reference'),
            ['end_to_end_reference'],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_transactions_merged_into'), ['merged_into'], unique=False
        )

    op.create_table(
        'merge_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('groups', sa.JSON(), nullable=True),
        sa.Column('refused', sa.JSON(), nullable=True),
        sa.Column('summary', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_merge_reports_created_at'), 'merge_reports', ['created_at']
    )

    _backfill_the_reference()


def _backfill_the_reference() -> None:
    """Fill the new column from the stored structured description.

    The function reads each row that holds a structured description. It takes
    the canonical key, and otherwise the old key of the labelled parser.

    The function stores no reference that names no single payment, so that the
    column holds the same content as a later insert writes.
    """
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            'SELECT id, description_structured FROM transactions '
            'WHERE description_structured IS NOT NULL'
        )
    ).fetchall()

    updates = []
    for row_id, raw in rows:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for key in _REFERENCE_KEYS:
            value = data.get(key)
            if not isinstance(value, str):
                continue
            value = value.strip()
            if not value:
                continue
            # Remove each whitespace character first: an MT940 description
            # wraps at a fixed width and splits the value, as in
            # `NOTP ROVIDED`.
            if ''.join(value.split()).upper() in _UNUSABLE_REFERENCES:
                break
            updates.append({'row_id': row_id, 'value': value})
            break

    if updates:
        conn.execute(
            sa.text(
                'UPDATE transactions SET end_to_end_reference = :value '
                'WHERE id = :row_id'
            ),
            updates,
        )


def downgrade() -> None:
    op.drop_index(op.f('ix_merge_reports_created_at'), table_name='merge_reports')
    op.drop_table('merge_reports')

    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transactions_merged_into'))
        batch_op.drop_index(batch_op.f('ix_transactions_end_to_end_reference'))
        batch_op.drop_column('merged_into')
        batch_op.drop_column('end_to_end_reference')
