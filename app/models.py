"""Modelos persistentes: eventos de estudo nunca são apagados no refresh."""
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    topics: Mapped[list["Topic"]] = relationship(back_populates="subject")


class NovelPractice(Base):
    """Resultados inéditos por matéria; SEM assunto e sem tentativas individuais."""
    __tablename__ = 'novel_practice'
    __table_args__ = (
        CheckConstraint('total >= 1 AND total <= 10000', name='ck_novel_practice_total'),
        CheckConstraint('correct >= 0 AND correct <= total', name='ck_novel_practice_correct'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey('subjects.id', ondelete='RESTRICT'), nullable=False)
    practice_date: Mapped[date] = mapped_column(Date(), nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    correct: Mapped[int] = mapped_column(Integer, nullable=False)
    exam_conditions: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    no_consultation: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    distinct_questions: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("subject_id", "code", name="uq_topic_subject_code"), CheckConstraint("importance BETWEEN 1 AND 5", name="ck_topic_importance"))
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subject: Mapped[Subject] = relationship(back_populates="topics")


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="RESTRICT"), nullable=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    choices: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    topic: Mapped[Topic | None] = relationship()


class StudySession(Base):
    __tablename__ = "study_sessions"
    __table_args__ = (CheckConstraint("status IN ('open', 'closed')", name="ck_session_status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="open", nullable=False)
    refresh_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class TopicReview(Base):
    __tablename__ = "topic_reviews"
    __table_args__ = (UniqueConstraint("session_id", "topic_id", name="uq_session_topic_review"), CheckConstraint("grade BETWEEN 0 AND 4", name="ck_review_grade"))
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("study_sessions.id", ondelete="RESTRICT"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False)
    grade: Mapped[int] = mapped_column(Integer, nullable=False)
    recall_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accuracy_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assistance_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    application_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gap_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    critical_gap: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    explained_without_consulting: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    applied_to_new_questions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class QuestionAttempt(Base):
    __tablename__ = "question_attempts"
    __table_args__ = (UniqueConstraint("session_id", "question_id", name="uq_session_question_attempt"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("study_sessions.id", ondelete="RESTRICT"), nullable=False)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NewContentLog(Base):
    __tablename__ = "new_content_logs"
    __table_args__ = (CheckConstraint("minutes BETWEEN 1 AND 180", name="ck_new_content_minutes"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("study_sessions.id", ondelete="RESTRICT"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False)
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recall_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accuracy_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gap_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuthSession(Base):
    """Sessão de login revogável. Guardamos somente o hash do token."""
    __tablename__ = "auth_sessions"
    token_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class RetentionProfile(Base):
    """Audit trail of an independently calibrated FSRS model by subject and item type.

    JSON metrics are diagnostics; never store a claim of scientifically proven
    individual retention or assign novel practice to individual subjects.
    """
    __tablename__ = 'retention_profiles'
    scope: Mapped[str] = mapped_column(String(80), primary_key=True)
    stage: Mapped[str] = mapped_column(String(20), nullable=False, default='observando')
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    factor: Mapped[float] = mapped_column(default=1.0, nullable=False)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # Separate 21-weight optimizer state; lightweight v0.15 fields remain backwards compatible.
    optimizer_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    optimizer_parameters: Mapped[list | None] = mapped_column(JSON, nullable=True)
    optimizer_status: Mapped[str] = mapped_column(String(32), default='aguardando', nullable=False)
    optimizer_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    optimizer_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class RetentionModelRun(Base):
    """Historical calibration snapshots for reproducible diagnostics."""
    __tablename__ = 'retention_model_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey('study_sessions.id', ondelete='RESTRICT'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    factor: Mapped[float] = mapped_column(nullable=False)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
