"""Validação dos dados recebidos pela API."""
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class NovelPracticeIn(BaseModel):
    subject_id: int
    practice_date: date
    total: int = Field(ge=1, le=10000)
    correct: int = Field(ge=0, le=10000)
    exam_conditions: bool | None = None
    no_consultation: bool | None = None
    distinct_questions: bool | None = None

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
    # Clientes anteriores continuam aceitos; questionários v0.13 e v0.14 inferem a nota.
    grade: int | None = Field(default=None, ge=0, le=4)
    recall_level: int | None = Field(default=None, ge=0, le=3)
    accuracy_level: int | None = Field(default=None, ge=0, le=3)
    assistance_level: int | None = Field(default=None, ge=0, le=3)
    application_level: int | None = Field(default=None, ge=0, le=2)
    gap_level: int | None = Field(default=None, ge=0, le=3)

    @model_validator(mode='after')
    def validate_assessment(self):
        fields = (self.recall_level, self.accuracy_level, self.assistance_level, self.gap_level)
        if any(v is not None for v in fields):
            if not all(v is not None for v in fields):
                raise ValueError('Responda todas as quatro perguntas do questionário de revisão.')
            if self.grade is not None:
                raise ValueError('Nota é inferida automaticamente; não envie nota manual junto ao questionário.')
            if self.application_level is not None and self.applied_to_new_questions:
                if self.application_level != 2:
                    raise ValueError('Aplicação independente contradiz o resultado declarado.')
        elif self.grade is None:
            raise ValueError('Informe o questionário completo ou a nota do formulário anterior.')
        elif self.application_level is not None:
            raise ValueError('Aplicação v0.14 requer o questionário estruturado completo.')
        return self
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
    recall_level: int | None = Field(default=None, ge=0, le=3)
    accuracy_level: int | None = Field(default=None, ge=0, le=3)
    gap_level: int | None = Field(default=None, ge=0, le=3)
    notes: str | None = Field(default=None, max_length=3000)

    @model_validator(mode='after')
    def validate_initial_assessment(self):
        values = (self.recall_level, self.accuracy_level, self.gap_level)
        if any(v is not None for v in values) and not all(v is not None for v in values):
            raise ValueError('Responda as três perguntas do estudo inicial.')
        return self


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    opened_at: datetime
    refreshed_at: datetime | None
    status: str
    refresh_summary: dict | None = None
