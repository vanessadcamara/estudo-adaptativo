"""Expand retention model run stages for full optimizer statuses."""
from alembic import op
import sqlalchemy as sa

revision = '0012_expand_retention_run_stage'
down_revision = '0011_v16_full_fsrs_optimizer'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('retention_model_runs') as batch:
        batch.alter_column('stage', existing_type=sa.String(20), type_=sa.String(64),
                           existing_nullable=False)


def downgrade():
    with op.batch_alter_table('retention_model_runs') as batch:
        batch.alter_column('stage', existing_type=sa.String(64), type_=sa.String(20),
                           existing_nullable=False)
