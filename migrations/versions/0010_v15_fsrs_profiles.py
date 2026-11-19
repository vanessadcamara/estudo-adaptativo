"""v0.15: FSRS model diagnostics and activation state; preserves all event histories.

Revision ID: 0010_v15_fsrs_profiles
Revises: 0009_v14_application_retention
"""
from alembic import op
import sqlalchemy as sa

revision = '0010_v15_fsrs_profiles'
down_revision = '0009_v14_application_retention'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('retention_profiles',
        sa.Column('scope', sa.String(length=80), primary_key=True),
        sa.Column('stage', sa.String(length=20), nullable=False, server_default='observando'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('factor', sa.Float(), nullable=False, server_default='1'),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table('retention_model_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('scope', sa.String(length=80), nullable=False),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('study_sessions.id', ondelete='RESTRICT')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('stage', sa.String(length=20), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('factor', sa.Float(), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=True),
    )
    op.create_index('ix_retention_model_runs_scope', 'retention_model_runs', ['scope'])


def downgrade():
    op.drop_index('ix_retention_model_runs_scope', table_name='retention_model_runs')
    op.drop_table('retention_model_runs')
    op.drop_table('retention_profiles')
