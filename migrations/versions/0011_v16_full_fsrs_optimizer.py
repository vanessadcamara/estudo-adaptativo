"""v0.16: isolated full FSRS-6 parameter optimization, retaining v0.15 history.

Revision ID: 0011_v16_full_fsrs_optimizer
Revises: 0010_v15_fsrs_profiles
"""
from alembic import op
import sqlalchemy as sa

revision = '0011_v16_full_fsrs_optimizer'
down_revision = '0010_v15_fsrs_profiles'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('retention_profiles') as batch:
        batch.add_column(sa.Column('optimizer_active', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column('optimizer_parameters', sa.JSON(), nullable=True))
        batch.add_column(sa.Column('optimizer_status', sa.String(32), nullable=False, server_default='aguardando'))
        batch.add_column(sa.Column('optimizer_metrics', sa.JSON(), nullable=True))
        batch.add_column(sa.Column('optimizer_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('retention_profiles') as batch:
        batch.drop_column('optimizer_updated_at')
        batch.drop_column('optimizer_metrics')
        batch.drop_column('optimizer_status')
        batch.drop_column('optimizer_parameters')
        batch.drop_column('optimizer_active')
