"""add hidden and archived_at to models

Revision ID: 0003_model_hidden
Revises: 0002_flat_materials
Create Date: 2026-09-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003_model_hidden'
down_revision: Union[str, None] = '0002_flat_materials'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('models', sa.Column('hidden', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('models', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('models', 'archived_at')
    op.drop_column('models', 'hidden')
