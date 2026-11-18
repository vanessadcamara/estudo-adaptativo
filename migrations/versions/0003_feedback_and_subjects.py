"""Feedback detalhado, matéria por questão e duração opcional.

Revision ID: 0003_feedback_and_subjects
Revises: 0002_auth_sessions
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_feedback_and_subjects"
down_revision = "0002_auth_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("questions", sa.Column("subject_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_questions_subject_id", "questions", "subjects", ["subject_id"], ["id"], ondelete="RESTRICT")
    op.execute("UPDATE questions SET subject_id = (SELECT subject_id FROM topics WHERE topics.id=questions.topic_id) WHERE topic_id IS NOT NULL")
    op.create_index("ix_questions_subject_id", "questions", ["subject_id"])
    op.add_column("topic_reviews", sa.Column("difficulty", sa.Integer(), nullable=True))
    op.add_column("topic_reviews", sa.Column("critical_gap", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.create_check_constraint("ck_topic_difficulty", "topic_reviews", "difficulty BETWEEN 1 AND 3")
    op.add_column("question_attempts", sa.Column("confidence", sa.Integer(), nullable=True))
    op.add_column("question_attempts", sa.Column("error_type", sa.String(length=24), nullable=True))
    op.create_check_constraint("ck_question_confidence", "question_attempts", "confidence BETWEEN 1 AND 3")
    op.alter_column("new_content_logs", "minutes", existing_type=sa.Integer(), nullable=True)


def downgrade():
    # Reverter remove novos feedbacks. Nunca executar em produção sem backup.
    op.alter_column("new_content_logs", "minutes", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint("ck_question_confidence", "question_attempts", type_="check")
    op.drop_column("question_attempts", "error_type")
    op.drop_column("question_attempts", "confidence")
    op.drop_constraint("ck_topic_difficulty", "topic_reviews", type_="check")
    op.drop_column("topic_reviews", "critical_gap")
    op.drop_column("topic_reviews", "difficulty")
    op.drop_index("ix_questions_subject_id", table_name="questions")
    op.drop_constraint("fk_questions_subject_id", "questions", type_="foreignkey")
    op.drop_column("questions", "subject_id")
