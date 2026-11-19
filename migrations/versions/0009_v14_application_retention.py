"""v0.14: status opcional de aplicação independente.

Revision ID: 0009_v14_application_retention
Revises: 0008_v13_assessments
"""
from alembic import op
import sqlalchemy as sa

revision = '0009_v14_application_retention'
down_revision = '0008_v13_assessments'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('topic_reviews') as batch:
        batch.add_column(sa.Column('application_level', sa.Integer(), nullable=True))
        batch.create_check_constraint('ck_topic_review_application_level',
                                      'application_level IN (0, 1, 2) OR application_level IS NULL')


def downgrade():
    with op.batch_alter_table('topic_reviews') as batch:
        batch.drop_constraint('ck_topic_review_application_level', type_='check')
        batch.drop_column('application_level')
