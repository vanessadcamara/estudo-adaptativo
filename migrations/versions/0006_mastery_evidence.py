"""Confirmações explícitas da estudante para o domínio (mantém todo histórico).

Revision ID: 0006_mastery_evidence
Revises: 0005_catalog_archives
"""
from alembic import op
import sqlalchemy as sa

revision = '0006_mastery_evidence'
down_revision = '0005_catalog_archives'
branch_labels = None
depends_on = None


def upgrade():
    # Eventos antigos permanecem; não se presume comprovação que não foi registrada.
    op.add_column('topic_reviews', sa.Column('explained_without_consulting', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('topic_reviews', sa.Column('applied_to_new_questions', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('topic_reviews', 'applied_to_new_questions')
    op.drop_column('topic_reviews', 'explained_without_consulting')
