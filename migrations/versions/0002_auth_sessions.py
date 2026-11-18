"""Sessões de autenticação (preserva todo o histórico existente)."""
from alembic import op
import sqlalchemy as sa

revision = "0002_auth_sessions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "auth_sessions",
        sa.Column("token_digest", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

def downgrade():
    op.drop_table("auth_sessions")
