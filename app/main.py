"""API + interface local do caderno adaptativo."""
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import (router as auth_router, find_session, require_login,
                      is_production, validate_auth_configuration)
from app.engine import build_queue
from app.assessment import inferred_grade
from app.performance import build_performance
from app.statistical_retention import public_profile, update_profiles, profiles_for_queue
from app.models import RetentionModelRun, NewContentLog, Question, QuestionAttempt, NovelPractice, StudySession, Subject, Topic, TopicReview, utcnow
from app.schemas import (NovelPracticeIn, NovelPracticeOut, NewContentIn, QuestionAttemptIn, QuestionIn, QuestionOut,
                         SessionOut, SubjectIn, SubjectOut, TopicIn, TopicOut, TopicReviewIn, QuestionArchiveIn, SubjectEdit, TopicEdit, QuestionEdit, ArchiveIn)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Sem valores de autenticação, recusa iniciar em qualquer ambiente.
    validate_auth_configuration()
    yield


app = FastAPI(title="Estudo Adaptativo BB", version="0.16.0", lifespan=lifespan,
              docs_url=None if is_production() else "/docs",
              redoc_url=None if is_production() else "/redoc",
              openapi_url=None if is_production() else "/openapi.json")
api = APIRouter(prefix="/api", dependencies=[Depends(require_login)])
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    )
    if is_production():
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path in {"/", "/login"} or request.url.path.startswith("/api/auth/") or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", include_in_schema=False)
def home(request: Request, db: Session = Depends(get_db)):
    if find_session(request, db) is None:
        return RedirectResponse("/login", status_code=303)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/login", include_in_schema=False)
def login_page(request: Request, db: Session = Depends(get_db)):
    if find_session(request, db):
        return RedirectResponse("/", status_code=303)
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(func.count()).select_from(Subject)).scalar_one()
    return {"status": "ok"}


@api.get('/novel-practice', response_model=list[NovelPracticeOut])
def list_novel_practice(include_archived: bool = False, subject_id: int | None = None,
                        db: Session = Depends(get_db)):
    query = select(NovelPractice)
    if not include_archived:
        query = query.where(NovelPractice.archived_at.is_(None))
    if subject_id is not None:
        query = query.where(NovelPractice.subject_id == subject_id)
    return db.scalars(query.order_by(NovelPractice.practice_date.desc(), NovelPractice.id.desc())).all()


def ensure_active_novel_subject(db: Session, subject_id: int):
    subject = db.get(Subject, subject_id)
    if subject is None or subject.archived_at is not None:
        raise HTTPException(404, 'Matéria ativa não encontrada.')


@api.post('/novel-practice', response_model=NovelPracticeOut, status_code=status.HTTP_201_CREATED)
def create_novel_practice(payload: NovelPracticeIn, db: Session = Depends(get_db)):
    ensure_active_novel_subject(db, payload.subject_id)
    item = NovelPractice(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@api.patch('/novel-practice/{record_id}', response_model=NovelPracticeOut)
def edit_novel_practice(record_id: int, payload: NovelPracticeIn, db: Session = Depends(get_db)):
    item = db.get(NovelPractice, record_id)
    if item is None or item.archived_at is not None:
        raise HTTPException(404, 'Registro ativo não encontrado.')
    ensure_active_novel_subject(db, payload.subject_id)
    item.subject_id = payload.subject_id
    item.practice_date = payload.practice_date
    item.total = payload.total
    item.correct = payload.correct
    item.exam_conditions = payload.exam_conditions
    item.no_consultation = payload.no_consultation
    item.distinct_questions = payload.distinct_questions
    item.updated_at = utcnow()
    db.commit()
    db.refresh(item)
    return item


@api.delete('/novel-practice/{record_id}', response_model=NovelPracticeOut)
def archive_novel_practice(record_id: int, db: Session = Depends(get_db)):
    item = db.get(NovelPractice, record_id)
    if item is None:
        raise HTTPException(404, 'Registro não encontrado.')
    if item.archived_at is None:
        item.archived_at = utcnow()
        item.updated_at = utcnow()
        db.commit()
        db.refresh(item)
    return item


@api.patch('/novel-practice/{record_id}/restore', response_model=NovelPracticeOut)
def restore_novel_practice(record_id: int, db: Session = Depends(get_db)):
    item = db.get(NovelPractice, record_id)
    if item is None:
        raise HTTPException(404, 'Registro não encontrado.')
    ensure_active_novel_subject(db, item.subject_id)
    if item.archived_at is not None:
        item.archived_at = None
        item.updated_at = utcnow()
        db.commit()
        db.refresh(item)
    return item


@api.get('/retention-models')
def retention_models(db: Session = Depends(get_db)):
    """Estatísticas da validação, sem expor eventos pessoais ou credenciais."""
    return [public_profile(p) for p in sorted(profiles_for_queue(db).values(), key=lambda x: x.scope)]


@api.get('/retention-models/history')
def retention_model_history(scope: str | None = Query(None, max_length=80),
                            limit: int = Query(50, ge=1, le=200),
                            db: Session = Depends(get_db)):
    query = select(RetentionModelRun)
    if scope is not None:
        query = query.where(RetentionModelRun.scope == scope)
    events = db.scalars(query.order_by(RetentionModelRun.created_at.desc(),
                                      RetentionModelRun.id.desc()).limit(limit)).all()
    return [{'id': r.id, 'scope': r.scope, 'session_id': r.session_id,
             'created_at': r.created_at.isoformat(), 'stage': r.stage,
             'active': r.active, 'factor': r.factor, 'metrics': r.metrics}
            for r in events]


@api.get('/performance')
def performance(db: Session = Depends(get_db)):
    return build_performance(db)


@api.get("/subjects", response_model=list[SubjectOut])
def list_subjects(include_archived: bool = False, db: Session = Depends(get_db)):
    query = select(Subject)
    if not include_archived:
        query = query.where(Subject.archived_at.is_(None))
    return db.scalars(query.order_by(Subject.name)).all()


@api.post("/subjects", response_model=SubjectOut, status_code=status.HTTP_201_CREATED)
def create_subject(payload: SubjectIn, db: Session = Depends(get_db)):
    if not payload.name.strip():
        raise HTTPException(422, "Informe o nome da matéria.")
    entry = Subject(name=payload.name.strip())
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Já existe uma matéria com este nome.")
    db.refresh(entry)
    return entry


@api.patch("/subjects/{subject_id}", response_model=SubjectOut)
def update_subject(subject_id: int, payload: SubjectEdit, db: Session = Depends(get_db)):
    item = db.get(Subject, subject_id)
    if not item:
        raise HTTPException(404, "Matéria não encontrada.")
    if not payload.name.strip():
        raise HTTPException(422, "Informe o nome da matéria.")
    item.name = payload.name.strip()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Já existe matéria com esse nome.")
    db.refresh(item)
    return item


@api.patch("/subjects/{subject_id}/archive", response_model=SubjectOut)
def archive_subject(subject_id: int, payload: ArchiveIn, db: Session = Depends(get_db)):
    item = db.get(Subject, subject_id)
    if not item:
        raise HTTPException(404, "Matéria não encontrada.")
    item.archived_at = utcnow() if payload.archived else None
    db.commit()
    db.refresh(item)
    return item


@api.get("/topics", response_model=list[TopicOut])
def list_topics(include_archived: bool = False, db: Session = Depends(get_db)):
    query = select(Topic)
    if not include_archived:
        query = query.where(Topic.archived_at.is_(None))
    return db.scalars(query.order_by(Topic.subject_id, Topic.code, Topic.title)).all()


@api.post("/topics", response_model=TopicOut, status_code=status.HTTP_201_CREATED)
def create_topic(payload: TopicIn, db: Session = Depends(get_db)):
    subject = db.get(Subject, payload.subject_id)
    if subject is None or subject.archived_at is not None:
        raise HTTPException(404, "Matéria ativa não encontrada.")
    if not payload.title.strip():
        raise HTTPException(422, "Informe o nome do assunto.")
    entry = Topic(subject_id=payload.subject_id, title=payload.title.strip(),
                  code=payload.code.strip() if payload.code else None, importance=payload.importance)
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Código de tópico já utilizado nessa matéria.")
    db.refresh(entry)
    return entry


@api.patch("/topics/{topic_id}", response_model=TopicOut)
def update_topic(topic_id: int, payload: TopicEdit, db: Session = Depends(get_db)):
    item = db.get(Topic, topic_id)
    if not item:
        raise HTTPException(404, "Assunto não encontrado.")
    subject = db.get(Subject, payload.subject_id)
    if subject is None or subject.archived_at is not None:
        raise HTTPException(404, "Matéria ativa não encontrada.")
    if not payload.title.strip():
        raise HTTPException(422, "Informe o nome do assunto.")
    former_subject_id = item.subject_id
    item.subject_id, item.title = payload.subject_id, payload.title.strip()
    item.code = payload.code.strip() if payload.code and payload.code.strip() else None
    item.importance = payload.importance
    try:
        if former_subject_id != payload.subject_id:
            # Mantém os links associados ao tópico coerentes após troca de disciplina.
            db.execute(update(Question).where(Question.topic_id == topic_id).values(subject_id=payload.subject_id))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Código já utilizado nesta matéria.")
    db.refresh(item)
    return item


@api.patch("/topics/{topic_id}/archive", response_model=TopicOut)
def archive_topic(topic_id: int, payload: ArchiveIn, db: Session = Depends(get_db)):
    item = db.get(Topic, topic_id)
    if not item:
        raise HTTPException(404, "Assunto não encontrado.")
    item.archived_at = utcnow() if payload.archived else None
    db.commit()
    db.refresh(item)
    return item


@api.get("/questions", response_model=list[QuestionOut])
def list_questions(include_archived: bool = False, db: Session = Depends(get_db)):
    query = select(Question)
    if not include_archived:
        query = query.where(Question.archived_at.is_(None))
    return db.scalars(query.order_by(Question.id.desc())).all()


@api.post("/questions", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
def create_question(payload: QuestionIn, db: Session = Depends(get_db)):
    if payload.topic_id is not None:
        topic = db.get(Topic, payload.topic_id)
        if topic is None or topic.archived_at is not None:
            raise HTTPException(404, "Assunto ativo não encontrado.")
    subject_id = payload.subject_id
    if subject_id is not None:
        subject = db.get(Subject, subject_id)
        if subject is None or subject.archived_at is not None:
            raise HTTPException(404, "Matéria ativa não encontrada.")
    if payload.topic_id is not None:
        topic = db.get(Topic, payload.topic_id)
        if subject_id is not None and topic.subject_id != subject_id:
            raise HTTPException(422, "O tópico não pertence à matéria selecionada.")
        subject_id = topic.subject_id
    entry = Question(url=str(payload.url) if payload.url else None,
                     statement=payload.statement.strip() if payload.statement else None,
                     choices=payload.choices, topic_id=payload.topic_id, subject_id=subject_id)
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Esta questão já está cadastrada.")
    db.refresh(entry)
    return entry


@api.patch("/questions/{question_id}", response_model=QuestionOut)
def update_question(question_id: int, payload: QuestionEdit, db: Session = Depends(get_db)):
    item = db.get(Question, question_id)
    if not item:
        raise HTTPException(404, "Questão não encontrada.")
    subject = db.get(Subject, payload.subject_id) if payload.subject_id is not None else None
    topic = db.get(Topic, payload.topic_id) if payload.topic_id is not None else None
    if payload.subject_id is not None and (subject is None or subject.archived_at is not None):
        raise HTTPException(404, "Matéria ativa não encontrada.")
    if payload.topic_id is not None:
        if topic is None or topic.archived_at is not None:
            raise HTTPException(404, "Assunto ativo não encontrado.")
        if subject and topic.subject_id != subject.id:
            raise HTTPException(422, "Assunto não pertence à matéria selecionada.")
    item.url = str(payload.url) if payload.url else None
    item.statement = payload.statement.strip() if payload.statement else None
    item.choices = payload.choices
    item.topic_id = payload.topic_id
    item.subject_id = topic.subject_id if topic else payload.subject_id
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Este link já está cadastrado.")
    db.refresh(item)
    return item


@api.patch("/questions/{question_id}/archive", response_model=QuestionOut)
def archive_question(question_id: int, payload: QuestionArchiveIn, db: Session = Depends(get_db)):
    """Retira/recoloca uma questão na pilha sem apagar nenhuma tentativa."""
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(404, "Questão não encontrada.")
    if payload.archived and question.archived_at is None:
        question.archived_at = utcnow()
    elif not payload.archived:
        question.archived_at = None
    db.commit()
    db.refresh(question)
    return question


@api.get("/sessions/open", response_model=SessionOut | None)
def get_open_session(db: Session = Depends(get_db)):
    return db.scalars(select(StudySession).where(StudySession.status == "open").order_by(StudySession.id.desc())).first()


@api.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def start_session(db: Session = Depends(get_db)):
    existing = db.scalars(select(StudySession).where(StudySession.status == "open")).first()
    if existing:
        return existing
    entry = StudySession()
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_open_session_or_409(db: Session, session_id: int) -> StudySession:
    entry = db.get(StudySession, session_id)
    if not entry:
        raise HTTPException(404, "Sessão não encontrada.")
    if entry.status != "open":
        raise HTTPException(409, "Sessão já fechada pelo refresh.")
    return entry


@api.get("/sessions/{session_id}/progress")
def session_progress(session_id: int, db: Session = Depends(get_db)):
    get_open_session_or_409(db, session_id)
    reviewed = db.scalars(select(TopicReview.topic_id).where(TopicReview.session_id == session_id)).all()
    answered = db.scalars(select(QuestionAttempt.question_id).where(QuestionAttempt.session_id == session_id)).all()
    return {"topics": reviewed, "questions": answered}


@api.get("/sessions/{session_id}/queue")
def session_queue(session_id: int, topic_minutes: int | None = Query(None, ge=0, le=180),
                  question_minutes: int | None = Query(None, ge=0, le=180),
                  subject_id: int | None = Query(None, ge=0), db: Session = Depends(get_db)):
    get_open_session_or_409(db, session_id)
    validate_queue_subject(db, subject_id)
    return build_queue(db, exclude_session_id=session_id, subject_id=subject_id,
                       topic_minutes=topic_minutes, question_minutes=question_minutes)


def validate_queue_subject(db: Session, subject_id: int | None) -> None:
    if subject_id is None or subject_id == 0:  # 0 = caixa legada de questões sem matéria
        return
    subject = db.get(Subject, subject_id)
    if subject is None or subject.archived_at is not None:
        raise HTTPException(404, 'Matéria ativa não encontrada.')


@api.get("/queue")
def preview_queue(topic_minutes: int | None = Query(None, ge=0, le=180),
                  question_minutes: int | None = Query(None, ge=0, le=180),
                  subject_id: int | None = Query(None, ge=0), db: Session = Depends(get_db)):
    # Sem subject_id, preserva contrato da API v0.6 para clientes antigos;
    # o estudo na interface v0.7 usa sempre uma matéria explicitamente escolhida.
    validate_queue_subject(db, subject_id)
    return build_queue(db, subject_id=subject_id,
                       topic_minutes=topic_minutes, question_minutes=question_minutes)


@api.post("/sessions/{session_id}/topic-reviews", status_code=status.HTTP_201_CREATED)
def record_topic_review(session_id: int, payload: TopicReviewIn, db: Session = Depends(get_db)):
    get_open_session_or_409(db, session_id)
    topic = db.get(Topic, payload.topic_id)
    if topic is None or topic.archived_at is not None:
        raise HTTPException(404, "Assunto ativo não encontrado.")
    # Estudo inicial e revisão são modalidades mutuamente exclusivas no mesmo ciclo.
    if db.scalar(select(NewContentLog.id).where(
        NewContentLog.session_id == session_id, NewContentLog.topic_id == payload.topic_id)) is not None:
        raise HTTPException(409, "Este assunto já foi estudado nesta sessão. Inicie outra para revisá-lo.")
    structured = payload.recall_level is not None
    grade = (inferred_grade(payload.recall_level, payload.accuracy_level,
                            payload.assistance_level, payload.gap_level,
                            application=payload.application_level)
             if structured else payload.grade)
    gap = payload.gap_level >= 2 if structured else payload.critical_gap
    explained = (grade == 4 and payload.assistance_level == 0 if structured
                 else payload.explained_without_consulting)
    entry = TopicReview(session_id=session_id, topic_id=payload.topic_id,
                        grade=grade, difficulty=payload.difficulty,
                        critical_gap=gap, explained_without_consulting=explained,
                        recall_level=payload.recall_level,
                        accuracy_level=payload.accuracy_level,
                        assistance_level=payload.assistance_level,
                        application_level=payload.application_level,
                        gap_level=payload.gap_level,
                        applied_to_new_questions=(payload.application_level == 2 and grade == 4
                                                  if payload.application_level is not None
                                                  else payload.applied_to_new_questions),
                        notes=payload.notes)
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Este tópico já recebeu nota nesta sessão.")
    return {"id": entry.id, "saved": True, "inferred_grade": entry.grade}


@api.post("/sessions/{session_id}/question-attempts", status_code=status.HTTP_201_CREATED)
def record_question_attempt(session_id: int, payload: QuestionAttemptIn, db: Session = Depends(get_db)):
    get_open_session_or_409(db, session_id)
    question = db.get(Question, payload.question_id)
    if question is None or question.archived_at is not None:
        raise HTTPException(404, "Questão ativa não encontrada.")
    entry = QuestionAttempt(session_id=session_id, question_id=payload.question_id,
                            is_correct=payload.is_correct, confidence=payload.confidence,
                            error_type=payload.error_type, notes=payload.notes)
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Esta questão já foi registrada nesta sessão.")
    return {"id": entry.id, "saved": True}


@api.post("/sessions/{session_id}/new-content", status_code=status.HTTP_201_CREATED)
def record_new_content(session_id: int, payload: NewContentIn, db: Session = Depends(get_db)):
    get_open_session_or_409(db, session_id)
    topic = db.get(Topic, payload.topic_id)
    if topic is None or topic.archived_at is not None:
        raise HTTPException(404, "Assunto ativo não encontrado.")
    if db.scalar(select(TopicReview.id).where(
        TopicReview.session_id == session_id, TopicReview.topic_id == payload.topic_id)) is not None:
        raise HTTPException(409, "Este assunto já foi revisado nesta sessão. Inicie outra para estudá-lo novamente.")
    existing = db.scalar(select(NewContentLog.id).where(
        NewContentLog.session_id == session_id, NewContentLog.topic_id == payload.topic_id))
    if existing is not None:
        raise HTTPException(409, "Este assunto já teve estudo inicial registrado nesta sessão.")
    entry = NewContentLog(session_id=session_id, topic_id=payload.topic_id,
                          minutes=payload.minutes, notes=payload.notes,
                          recall_level=payload.recall_level,
                          accuracy_level=payload.accuracy_level,
                          gap_level=payload.gap_level)
    db.add(entry)
    db.commit()
    return {"id": entry.id, "saved": True}


@api.post("/sessions/{session_id}/refresh", response_model=SessionOut)
def refresh_session(session_id: int, db: Session = Depends(get_db)):
    entry = get_open_session_or_409(db, session_id)
    # Apenas registros explícitos do estudante entram nas estatísticas.
    topic_grades = db.scalars(select(TopicReview.grade).where(TopicReview.session_id == session_id)).all()
    attempts = db.scalars(select(QuestionAttempt.is_correct).where(QuestionAttempt.session_id == session_id)).all()
    new_minutes = db.scalar(select(func.sum(NewContentLog.minutes)).where(NewContentLog.session_id == session_id)) or 0
    new_count = db.scalar(select(func.count()).select_from(NewContentLog).where(NewContentLog.session_id == session_id)) or 0
    summary = {
        "topics_reviewed": len(topic_grades), "questions_attempted": len(attempts),
        "questions_correct": sum(attempts), "questions_wrong": len(attempts) - sum(attempts),
        "new_content_minutes": new_minutes, "new_content_records": new_count,
        "grades": {str(n): topic_grades.count(n) for n in range(5)},
    }
    entry.status = "closed"
    entry.refreshed_at = utcnow()
    # Recalibração leve, automática e isolada por matéria e por tipo de item.
    # O fallback da v0.14 permanece até validação em dados não usados no treino.
    update_profiles(db, session_id=session_id)
    # Recalcula a fila para a próxima sessão sem zerar eventos anteriores.
    upcoming = build_queue(db)
    summary["next_due_topics"] = upcoming["due_topics"]
    summary["next_due_questions"] = upcoming["due_questions"]
    entry.refresh_summary = summary
    db.commit()
    db.refresh(entry)
    return entry


@api.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    queue = build_queue(db)
    last = db.scalars(select(StudySession).where(StudySession.status == "closed")
                      .order_by(StudySession.refreshed_at.desc()).limit(5)).all()
    return {
        "total_topics": queue["total_topics"], "total_questions": queue["total_questions"],
        "due_topics": queue["due_topics"], "due_questions": queue["due_questions"],
        "recent_sessions": [
            {"id": s.id, "opened_at": s.opened_at.isoformat(),
             "refreshed_at": s.refreshed_at.isoformat() if s.refreshed_at else None,
             "summary": s.refresh_summary}
            for s in last
        ],
    }


# Autenticação pública apenas em /login e /me; /logout exige login + CSRF.
app.include_router(auth_router)
app.include_router(api)
