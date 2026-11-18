"""API + interface local do caderno adaptativo."""
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import (router as auth_router, find_session, require_login,
                      is_production, validate_auth_configuration)
from app.engine import build_queue
from app.models import NewContentLog, Question, QuestionAttempt, StudySession, Subject, Topic, TopicReview, utcnow
from app.schemas import (NewContentIn, QuestionAttemptIn, QuestionIn, QuestionOut,
                         SessionOut, SubjectIn, SubjectOut, TopicIn, TopicOut, TopicReviewIn)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Sem valores de autenticação, recusa iniciar em qualquer ambiente.
    validate_auth_configuration()
    yield


app = FastAPI(title="Estudo Adaptativo BB", version="0.2.0", lifespan=lifespan,
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
    if request.url.path in {"/", "/login"} or request.url.path.startswith("/api/auth/"):
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


@api.get("/subjects", response_model=list[SubjectOut])
def list_subjects(db: Session = Depends(get_db)):
    return db.scalars(select(Subject).order_by(Subject.name)).all()


@api.post("/subjects", response_model=SubjectOut, status_code=status.HTTP_201_CREATED)
def create_subject(payload: SubjectIn, db: Session = Depends(get_db)):
    entry = Subject(name=payload.name.strip())
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Já existe uma matéria com este nome.")
    db.refresh(entry)
    return entry


@api.get("/topics", response_model=list[TopicOut])
def list_topics(db: Session = Depends(get_db)):
    return db.scalars(select(Topic).order_by(Topic.subject_id, Topic.code, Topic.title)).all()


@api.post("/topics", response_model=TopicOut, status_code=status.HTTP_201_CREATED)
def create_topic(payload: TopicIn, db: Session = Depends(get_db)):
    if not db.get(Subject, payload.subject_id):
        raise HTTPException(404, "Matéria não encontrada.")
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


@api.get("/questions", response_model=list[QuestionOut])
def list_questions(db: Session = Depends(get_db)):
    return db.scalars(select(Question).order_by(Question.id.desc())).all()


@api.post("/questions", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
def create_question(payload: QuestionIn, db: Session = Depends(get_db)):
    if payload.topic_id is not None and not db.get(Topic, payload.topic_id):
        raise HTTPException(404, "Tópico não encontrado.")
    entry = Question(url=str(payload.url) if payload.url else None,
                     statement=payload.statement.strip() if payload.statement else None,
                     choices=payload.choices, topic_id=payload.topic_id)
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Esta questão já está cadastrada.")
    db.refresh(entry)
    return entry


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


@api.get("/sessions/{session_id}/queue")
def session_queue(session_id: int, topic_minutes: int = Query(40, ge=0, le=180),
                  question_minutes: int = Query(20, ge=0, le=180), db: Session = Depends(get_db)):
    get_open_session_or_409(db, session_id)
    return build_queue(db, exclude_session_id=session_id,
                       topic_minutes=topic_minutes, question_minutes=question_minutes)


@api.get("/queue")
def preview_queue(topic_minutes: int = Query(40, ge=0, le=180),
                  question_minutes: int = Query(20, ge=0, le=180), db: Session = Depends(get_db)):
    return build_queue(db, topic_minutes=topic_minutes, question_minutes=question_minutes)


@api.post("/sessions/{session_id}/topic-reviews", status_code=status.HTTP_201_CREATED)
def record_topic_review(session_id: int, payload: TopicReviewIn, db: Session = Depends(get_db)):
    get_open_session_or_409(db, session_id)
    if not db.get(Topic, payload.topic_id):
        raise HTTPException(404, "Tópico não encontrado.")
    entry = TopicReview(session_id=session_id, topic_id=payload.topic_id,
                        grade=payload.grade, notes=payload.notes)
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Este tópico já recebeu nota nesta sessão.")
    return {"id": entry.id, "saved": True}


@api.post("/sessions/{session_id}/question-attempts", status_code=status.HTTP_201_CREATED)
def record_question_attempt(session_id: int, payload: QuestionAttemptIn, db: Session = Depends(get_db)):
    get_open_session_or_409(db, session_id)
    if not db.get(Question, payload.question_id):
        raise HTTPException(404, "Questão não encontrada.")
    entry = QuestionAttempt(session_id=session_id, question_id=payload.question_id,
                            is_correct=payload.is_correct, notes=payload.notes)
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
    if not db.get(Topic, payload.topic_id):
        raise HTTPException(404, "Tópico não encontrado.")
    entry = NewContentLog(session_id=session_id, topic_id=payload.topic_id,
                          minutes=payload.minutes, notes=payload.notes)
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
    summary = {
        "topics_reviewed": len(topic_grades), "questions_attempted": len(attempts),
        "questions_correct": sum(attempts), "questions_wrong": len(attempts) - sum(attempts),
        "new_content_minutes": new_minutes,
        "grades": {str(n): topic_grades.count(n) for n in range(5)},
    }
    entry.status = "closed"
    entry.refreshed_at = utcnow()
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
            {"id": s.id, "opened_at": s.opened_at.isoformat(), "summary": s.refresh_summary}
            for s in last
        ],
    }


# Autenticação pública apenas em /login e /me; /logout exige login + CSRF.
app.include_router(auth_router)
app.include_router(api)
