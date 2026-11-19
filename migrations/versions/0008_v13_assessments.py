"""v0.13: structured self-assessment and conditions of novel practice.

Revision ID: 0008_v13_assessments
Revises: 0007_novel_practice
"""
from alembic import op
import sqlalchemy as sa

revision = '0008_v13_assessments'
down_revision = '0007_novel_practice'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('topic_reviews') as batch:
        batch.add_column(sa.Column('recall_level', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('accuracy_level', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('assistance_level', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('gap_level', sa.Integer(), nullable=True))
    with op.batch_alter_table('new_content_logs') as batch:
        batch.add_column(sa.Column('recall_level', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('accuracy_level', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('gap_level', sa.Integer(), nullable=True))
    with op.batch_alter_table('novel_practice') as batch:
        batch.add_column(sa.Column('exam_conditions', sa.Boolean(), nullable=True))
        batch.add_column(sa.Column('no_consultation', sa.Boolean(), nullable=True))
        batch.add_column(sa.Column('distinct_questions', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('novel_practice') as batch:
        for key in ('exam_conditions', 'no_consultation', 'distinct_questions'):
            batch.drop_column(key)
    with op.batch_alter_table('new_content_logs') as batch:
        for key in ('recall_level', 'accuracy_level', 'gap_level'):
            batch.drop_column(key)
    with op.batch_alter_table('topic_reviews') as batch:
        for key in ('recall_level', 'accuracy_level', 'assistance_level', 'gap_level'):
            batch.drop_column(key)
