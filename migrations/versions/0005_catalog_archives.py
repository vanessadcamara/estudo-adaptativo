"""Arquivamento reversível de matérias e assuntos sem excluir histórico."""
from alembic import op
import sqlalchemy as sa

revision = "0005_catalog_archives"
down_revision = "0004_archive_questions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("subjects", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("topics", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    # Reverter remove a indicação de arquivamento, preservando registros.
    op.drop_column("topics", "archived_at")
    op.drop_column("subjects", "archived_at")
