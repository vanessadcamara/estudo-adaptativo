"""Arquivamento reversível de questões (sem perda do histórico).

Revision ID: 0004_archive_questions
Revises: 0003_feedback_and_subjects
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_archive_questions"
down_revision = "0003_feedback_and_subjects"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("questions", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))

def downgrade():
    op.drop_column("questions", "archived_at")
