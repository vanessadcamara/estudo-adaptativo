"""Esquema inicial e histórico de eventos.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "subjects", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "topics", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject_id", sa.Integer(), sa.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(30)), sa.Column("title", sa.String(240), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("subject_id", "code", name="uq_topic_subject_code"),
        sa.CheckConstraint("importance BETWEEN 1 AND 5", name="ck_topic_importance"),
    )
    op.create_table(
        "questions", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="RESTRICT")),
        sa.Column("url", sa.Text(), unique=True), sa.Column("statement", sa.Text()),
        sa.Column("choices", sa.JSON()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "study_sessions", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(12), nullable=False), sa.Column("refresh_summary", sa.JSON()),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_session_status"),
    )
    op.create_table(
        "topic_reviews", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("study_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False), sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "topic_id", name="uq_session_topic_review"),
        sa.CheckConstraint("grade BETWEEN 0 AND 4", name="ck_review_grade"),
    )
    op.create_table(
        "question_attempts", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("study_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False), sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "question_id", name="uq_session_question_attempt"),
    )
    op.create_table(
        "new_content_logs", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("study_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False), sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("minutes BETWEEN 1 AND 180", name="ck_new_content_minutes"),
    )


def downgrade():
    # Cuidado: reverter a migration elimina TODO o histórico. Não execute em produção.
    for name in ("new_content_logs", "question_attempts", "topic_reviews", "study_sessions", "questions", "topics", "subjects"):
        op.drop_table(name)
