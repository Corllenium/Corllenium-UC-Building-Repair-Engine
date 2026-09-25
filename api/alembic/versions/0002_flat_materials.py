"""add flat_materials to model_versions

Revision ID: 0002_flat_materials
Revises: 0001_initial
Create Date: 2026-09-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002_flat_materials'
down_revision: Union[str, None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('model_versions', sa.Column('flat_materials', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('model_versions', 'flat_materials')
