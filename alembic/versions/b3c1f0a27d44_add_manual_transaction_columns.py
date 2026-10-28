"""add is_manual and deleted_at to transactions

Revision ID: b3c1f0a27d44
Revises: 7dd060546159
Create Date: 2026-10-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c1f0a27d44'
down_revision: Union[str, None] = '7dd060546159'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_manual', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_transactions_deleted_at'), ['deleted_at'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transactions_deleted_at'))
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('is_manual')
