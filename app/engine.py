"""Cálculo adaptativo, orientado por eventos reais (sem punição por dias sem estudo)."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NewContentLog, Question, QuestionAttempt, Topic, TopicReview


def aware(dt: datetime) -> datetime:
    """SQLite em testes pode devolver datetime sem fuso; PostgreSQL preserva o fuso."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def elapsed_days(then: datetime | None, now: datetime) -> float | None:
    return max(0.0, (aware(now) - aware(then)).total_seconds() / 86400) if then else None


def grade4_streak(records: list[TopicReview]) -> int:
    count = 0
    for record in reversed(records):
        if record.grade != 4:
            break
        count += 1
    return count


def topic_interval(records: list[TopicReview]) -> int:
    """Intervalos de 1 a 60 dias. Acertos não extinguem o tópico."""
    if not records:
        return 1
    grade = records[-1].grade
    if grade <= 2:
        return (1, 2, 4)[grade]
    if grade == 3:
        return 7
    streak = grade4_streak(records)
    return 60 if streak >= 3 else (30 if streak == 2 else 14)


def question_interval(records: list[QuestionAttempt]) -> int:
    if not records or not records[-1].is_correct:
        return 1
    streak = 0
    for record in reversed(records):
        if not record.is_correct:
            break
        streak += 1
    return (3, 7, 14, 30, 60)[min(streak - 1, 4)]


def is_topic_mastered(records: list[TopicReview], attempts: list[QuestionAttempt]) -> bool:
    """Critério conservador: 3 notas 4 espaçadas, questões variadas e sem lacuna grave atual."""
    if len(records) < 3 or grade4_streak(records) < 3:
        return False
    best = records[-3:]
    first_gap = elapsed_days(best[0].created_at, aware(best[1].created_at)) or 0
    second_gap = elapsed_days(best[1].created_at, aware(best[2].created_at)) or 0
    if first_gap < 1 or second_gap < 14 or second_gap <= first_gap:
        return False
    # Exige amostra variada: últimas respostas em >= 5 questões diferentes.
    last_by_question: dict[int, QuestionAttempt] = {}
    for attempt in attempts:
        last_by_question[attempt.question_id] = attempt
    if len(last_by_question) < 5 or len(attempts) < 8:
        return False
    rate = sum(int(r.is_correct) for r in last_by_question.values()) / len(last_by_question)
    return rate >= 0.85 and all(r.grade >= 3 for r in records[-3:])


def build_queue(db: Session, now: datetime | None = None, exclude_session_id: int | None = None,
                topic_minutes: int = 40, question_minutes: int = 20) -> dict[str, Any]:
    """Calcula na hora: a passagem de até 7+ dias só altera a urgência, sem criar faltas."""
    if topic_minutes < 0 or question_minutes < 0 or topic_minutes > 180 or question_minutes > 180:
        raise ValueError("Tempo de fila inválido.")
    now = now or datetime.now(timezone.utc)
    topics = db.scalars(select(Topic).order_by(Topic.id)).all()
    questions = db.scalars(select(Question).order_by(Question.id)).all()
    topic_reviews = db.scalars(select(TopicReview).order_by(TopicReview.created_at, TopicReview.id)).all()
    attempts = db.scalars(select(QuestionAttempt).order_by(QuestionAttempt.created_at, QuestionAttempt.id)).all()
    new_content = db.scalars(select(NewContentLog).order_by(NewContentLog.created_at, NewContentLog.id)).all()
    by_topic: dict[int, list[TopicReview]] = defaultdict(list)
    by_question: dict[int, list[QuestionAttempt]] = defaultdict(list)
    question_by_topic: dict[int, list[QuestionAttempt]] = defaultdict(list)
    latest_study: dict[int, datetime] = {}
    for item in topic_reviews:
        by_topic[item.topic_id].append(item)
    for item in attempts:
        by_question[item.question_id].append(item)
    topic_for_question = {q.id: q.topic_id for q in questions}
    for item in attempts:
        topic_id = topic_for_question.get(item.question_id)
        if topic_id is not None:
            question_by_topic[topic_id].append(item)
    for item in new_content:
        latest_study[item.topic_id] = item.created_at
    topic_queue = []
    for t in topics:
        history = by_topic[t.id]
        if exclude_session_id is not None and any(r.session_id == exclude_session_id for r in history):
            continue
        last = history[-1] if history else None
        # Uma aula nova só fica elegível para revisão 1 dia depois, se ainda não há nota.
        reference = last.created_at if last else latest_study.get(t.id)
        days = elapsed_days(reference, now)
        interval = topic_interval(history)
        ratio = 1.0 if days is None else days / interval
        due = ratio >= 1
        difficulty = (4 - last.grade) / 4 if last else 0.5
        errors = sum(r.grade <= 2 for r in history) / len(history) if history else 0.5
        # Fórmula transparente, com cada fator entre 0 e 1.
        priority = 0.35 * difficulty + 0.30 * min(1, ratio) + 0.25 * errors + 0.10 * t.importance / 5
        mastered = is_topic_mastered(history, question_by_topic[t.id])
        topic_queue.append({
            "id": t.id, "subject_id": t.subject_id, "code": t.code, "title": t.title,
            "grade": last.grade if last else None, "attempts": len(history),
            "days_since": round(days, 1) if days is not None else None,
            "interval_days": interval, "due": due, "mastered": mastered,
            "priority": round(priority, 4), "estimated_minutes": 10,
            "reason": ("Ainda não revisado" if not last else ("Revisão atrasada" if due else "Manutenção programada")),
        })
    question_queue = []
    for q in questions:
        history = by_question[q.id]
        if exclude_session_id is not None and any(r.session_id == exclude_session_id for r in history):
            continue
        last = history[-1] if history else None
        days = elapsed_days(last.created_at, now) if last else None
        interval = question_interval(history)
        ratio = 1.0 if days is None else days / interval
        due = ratio >= 1
        correct = sum(int(r.is_correct) for r in history)
        errors = len(history) - correct
        # Laplace: não supõe domínio com um único acerto.
        smoothed_success = (correct + 1) / (len(history) + 2)
        wrong_rate = errors / len(history) if history else 0.5
        repeated_errors = sum(not r.is_correct for r in history[-3:]) >= 2
        uncertainty = 2 / (len(history) + 2)
        priority = (0.40 * (1 - smoothed_success) + 0.25 * wrong_rate +
                    0.25 * min(1, ratio) + 0.10 * uncertainty)
        if repeated_errors:
            priority += 0.10
        question_queue.append({
            "id": q.id, "topic_id": q.topic_id, "url": q.url,
            "statement": q.statement, "attempts": len(history), "errors": errors,
            "last_correct": last.is_correct if last else None,
            "days_since": round(days, 1) if days is not None else None,
            "interval_days": interval, "due": due, "priority": round(priority, 4),
            "estimated_minutes": 5,
            "reason": "Erros recorrentes" if repeated_errors else ("Pendente" if not history else ("Retentar" if not last.is_correct else "Manutenção")),
        })
    # Priorização por vencimento e dificuldade; não revisados não desaparecem da fila.
    topic_queue.sort(key=lambda x: (not x["due"], -x["priority"], x["id"]))
    question_queue.sort(key=lambda x: (not x["due"], -x["priority"], x["id"]))
    return {
        "topic_minutes": topic_minutes, "question_minutes": question_minutes,
        "topics": topic_queue[:topic_minutes // 10],
        "questions": question_queue[:question_minutes // 5],
        "total_topics": len(topics), "total_questions": len(questions),
        "due_topics": sum(x["due"] for x in topic_queue),
        "due_questions": sum(x["due"] for x in question_queue),
        "generated_at": now.isoformat(),
        "note": "Itens não realizados não recebem nota nem erro. A fila é recalculada pelo tempo decorrido.",
    }
