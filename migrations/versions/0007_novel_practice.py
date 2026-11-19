"""Registros agregados de questões inéditas sem associação a assuntos.

Revision ID: 0007_novel_practice
Revises: 0006_mastery_evidence
"""
from alembic import op
import sqlalchemy as sa

revision = '0007_novel_practice'
down_revision = '0006_mastery_evidence'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'novel_practice',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subjects.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('practice_date', sa.Date(), nullable=False),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('correct', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('total >= 1 AND total <= 10000', name='ck_novel_practice_total'),
        sa.CheckConstraint('correct >= 0 AND correct <= total', name='ck_novel_practice_correct'),
    )
    op.create_index('ix_novel_practice_subject_date', 'novel_practice', ['subject_id', 'practice_date'])


def downgrade():
    op.drop_index('ix_novel_practice_subject_date', table_name='novel_practice')
    op.drop_table('novel_practice')
