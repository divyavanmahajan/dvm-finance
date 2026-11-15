"""allow several budgets for one category and period

Revision ID: e4b7d2a91c36
Revises: c81a4f73be20
Create Date: 2026-11-15 00:00:00.000000

The unique index on (category, period) becomes a plain index. The application
now stops an overlap of the validity ranges instead.

The downgrade creates the unique index again. It fails when one category and
period hold two budgets. Delete or merge such budgets before a downgrade.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e4b7d2a91c36'
down_revision: Union[str, None] = 'c81a4f73be20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('budgets', schema=None) as batch_op:
        batch_op.drop_index('idx_budgets_category_period')
        batch_op.create_index(
            'idx_budgets_category_period', ['category', 'period'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('budgets', schema=None) as batch_op:
        batch_op.drop_index('idx_budgets_category_period')
        batch_op.create_index(
            'idx_budgets_category_period', ['category', 'period'], unique=True
        )
