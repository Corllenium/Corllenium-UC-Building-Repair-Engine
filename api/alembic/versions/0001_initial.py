"""Initial schema with seeded issue types

Revision ID: 0001_initial
Revises: 
Create Date: 2026-09-22 20:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'models',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('source_file', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_models_name'), 'models', ['name'], unique=True)

    op.create_table(
        'model_versions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('model_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('asset_sha256', sa.String(length=64), nullable=True),
        sa.Column('tri_count', sa.Integer(), nullable=False),
        sa.Column('coord_quantum', sa.JSON(), nullable=True),
        sa.Column('origin_offset', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['model_id'], ['models.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_model_versions_model_id'), 'model_versions', ['model_id'], unique=False)
    op.create_index(op.f('ix_model_versions_sha256'), 'model_versions', ['sha256'], unique=False)

    op.create_table(
        'version_assets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('version_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['version_id'], ['model_versions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_version_assets_version_id'), 'version_assets', ['version_id'], unique=False)

    op.create_table(
        'issue_types',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('default_action', sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint('key')
    )

    op.create_table(
        'fix_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('version_id', sa.Integer(), nullable=False),
        sa.Column('fixed_version_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('report_json', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['fixed_version_id'], ['model_versions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['version_id'], ['model_versions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_fix_runs_version_id'), 'fix_runs', ['version_id'], unique=False)

    # Seed issue_types
    meta = sa.MetaData()
    issue_types_table = sa.Table('issue_types', meta, autoload_with=op.get_bind())
    op.bulk_insert(
        issue_types_table,
        [
            {
                'key': 'degenerate',
                'name': 'Degenerate Triangles',
                'description': 'Zero-area triangles, collapsed edges, and loose vertices.',
                'default_action': 'auto_fix',
            },
            {
                'key': 'excess_subdivision',
                'name': 'Excess Subdivision / Gridlines',
                'description': 'Flat coplanar regions fragmented into micro-triangles by SketchUp gridlines.',
                'default_action': 'auto_fix',
            },
            {
                'key': 'oriented_visibility',
                'name': 'Occluded / Reversed Geometry',
                'description': 'Faces entirely hidden inside slabs or reversed facing away from view.',
                'default_action': 'auto_fix',
            },
            {
                'key': 'coplanar_overlap',
                'name': 'Coplanar Overlaps / Z-Fighting',
                'description': 'Overlapping same-facing coplanar faces competing for pixels.',
                'default_action': 'review',
            },
            {
                'key': 'double_sided_pair',
                'name': 'Thin-Sheet Double-Sided Pairs',
                'description': 'Opposite-facing coincident pairs forming thin architectural sheets.',
                'default_action': 'review',
            },
        ]
    )


def downgrade() -> None:
    op.drop_table('fix_runs')
    op.drop_table('issue_types')
    op.drop_table('version_assets')
    op.drop_table('model_versions')
    op.drop_table('models')
