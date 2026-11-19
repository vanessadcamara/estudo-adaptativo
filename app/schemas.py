"""Validação dos dados recebidos pela API."""
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class NovelPracticeIn(BaseModel):
    subject_id: int
    practice_date: date
    total: int = Field(ge=1, le=10000)
    correct: int = Field(ge=0, le=10000)

    @model_validator(mode='after')
    def validate_correct(self):
        if self.correct > self.total:
            raise ValueError('Os acertos não podem ultrapassar o total de questões.')
        return self


class NovelPracticeOut(NovelPracticeIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    archived_at: datetime | None = None


class SubjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class SubjectOut(SubjectIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    archived_at: datetime | None = None


class SubjectEdit(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class TopicIn(BaseModel):
    subject_id: int
    code: str | None = Field(default=None, max_length=30)
    title: str = Field(min_length=2, max_length=240)
    importance: int = Field(default=3, ge=1, le=5)


class TopicOut(TopicIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    archived_at: datetime | None = None


class TopicEdit(BaseModel):
    subject_id: int
    title: str = Field(min_length=2, max_length=240)
    code: str | None = Field(default=None, max_length=30)
    importance: int = Field(default=3, ge=1, le=5)


class QuestionIn(BaseModel):
    # Apenas URL já basta. Para conteúdo bloqueado por login, pode colar enunciado.
    url: HttpUrl | None = None
    statement: str | None = Field(default=None, min_length=3)
    choices: list[str] | None = None
    topic_id: int | None = None
    subject_id: int | None = None

    @model_validator(mode="after")
    def require_source(self):
        if not self.url and not (self.statement and self.statement.strip()):
            raise ValueError("Informe o link da questão ou cole o enunciado.")
        return self


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    url: str | None
    statement: str | None
    choices: list[str] | None
    topic_id: int | None
    subject_id: int | None
    archived_at: datetime | None = None


class QuestionEdit(QuestionIn):
    pass


class ArchiveIn(BaseModel):
    archived: bool


class QuestionArchiveIn(ArchiveIn):
    pass


class TopicReviewIn(BaseModel):
    topic_id: int
    grade: int = Field(ge=0, le=4)
    difficulty: int | None = Field(default=None, ge=1, le=3)
    critical_gap: bool = False
    explained_without_consulting: bool = False
    applied_to_new_questions: bool = False
    notes: str | None = Field(default=None, max_length=3000)


class QuestionAttemptIn(BaseModel):
    question_id: int
    is_correct: bool
    confidence: int | None = Field(default=None, ge=1, le=3)
    error_type: str | None = Field(default=None, pattern="^(concept|interpretation|attention|calculation|other)$")
    notes: str | None = Field(default=None, max_length=3000)


class NewContentIn(BaseModel):
    topic_id: int
    minutes: int | None = Field(default=None, ge=1, le=180)
    notes: str | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    opened_at: datetime
    refreshed_at: datetime | None
    status: str
    refresh_summary: dict | None = None
