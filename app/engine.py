"""Filas adaptativas: eventos reais, manutenção espaçada e cobertura completa.

Nunca cria faltas, notas, tentativas ou cronômetros para itens que não foram avaliados.
Atualiza prioridade com o tempo transcorrido, mesmo após semanas sem estudar.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NewContentLog, Question, QuestionAttempt, Topic, TopicReview, Subject


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def elapsed_days(then: datetime | None, now: datetime) -> float | None:
    return max(0.0, (aware(now) - aware(then)).total_seconds() / 86400) if then else None


def grade4_streak(records: list[TopicReview]) -> int:
    count = 0
    for record in reversed(records):
        if record.grade != 4 or getattr(record, 'critical_gap', False):
            break
        count += 1
    return count


def topic_interval(records: list[TopicReview]) -> int:
    """Revisão após 1–60 dias; não elimina tópicos consolidados."""
    if not records:
        return 1
    last = records[-1]
    if getattr(last, 'critical_gap', False):
        return 1
    if last.grade <= 2:
        base = (1, 2, 4)[last.grade]
    elif last.grade == 3:
        base = 7
    else:
        streak = grade4_streak(records)
        # Três notas 4 no mesmo dia não equivalem a memória consolidada.
        if streak >= 3:
            last_three = records[-3:]
            first_gap = elapsed_days(last_three[0].created_at, aware(last_three[1].created_at)) or 0
            second_gap = elapsed_days(last_three[1].created_at, aware(last_three[2].created_at)) or 0
            sufficiently_spaced = first_gap >= 1 and second_gap >= 14 and second_gap > first_gap
            base = 60 if sufficiently_spaced else 30
        else:
            base = 30 if streak == 2 else 14
    difficulty = getattr(last, 'difficulty', None)
    if difficulty == 3:
        return max(1, (base + 1) // 2)
    return min(60, base)


def question_interval(records: list[QuestionAttempt]) -> int:
    """Acertos com pouca confiança não são tratados como domínio."""
    if not records or not records[-1].is_correct:
        return 1
    last_confidence = getattr(records[-1], 'confidence', None)
    if last_confidence == 1:
        return 1
    if last_confidence == 2:
        return 2
    streak = 0
    for record in reversed(records):
        if not record.is_correct or getattr(record, 'confidence', None) in (1, 2):
            break
        streak += 1
    return (3, 7, 14, 30, 60)[min(max(0, streak - 1), 4)]


def is_topic_mastered(records: list[TopicReview], attempts: list[QuestionAttempt]) -> bool:
    """Exige domínio demonstrado em sessões espaçadas + questões variadas."""
    if len(records) < 3 or grade4_streak(records) < 3:
        return False
    last_three = records[-3:]
    first_gap = elapsed_days(last_three[0].created_at, aware(last_three[1].created_at)) or 0
    second_gap = elapsed_days(last_three[1].created_at, aware(last_three[2].created_at)) or 0
    if first_gap < 1 or second_gap < 14 or second_gap <= first_gap:
        return False
    last_by_question: dict[int, QuestionAttempt] = {}
    for attempt in attempts:
        last_by_question[attempt.question_id] = attempt
    if len(last_by_question) < 5 or len(attempts) < 8:
        return False
    confident_correct = sum(int(r.is_correct and getattr(r, 'confidence', None) != 1)
                            for r in last_by_question.values())
    rate = confident_correct / len(last_by_question)
    return rate >= 0.85 and all(r.grade >= 3 and not getattr(r, 'critical_gap', False)
                                for r in last_three)


def build_queue(db: Session, now: datetime | None = None, exclude_session_id: int | None = None,
                topic_minutes: int | None = None, question_minutes: int | None = None) -> dict[str, Any]:
    """Por padrão retorna o acervo INTEIRO, ordenado, sem corte por minutos.

    Limites por minutos só existem para compatibilidade com clientes anteriores
    que os solicitarem explicitamente. Não há relógio nem duração obrigatória.
    """
    for value in (topic_minutes, question_minutes):
        if value is not None and not (0 <= value <= 180):
            raise ValueError("Tempo de fila inválido.")
    now = aware(now or datetime.now(timezone.utc))
    active_subject_ids = set(db.scalars(select(Subject.id).where(Subject.archived_at.is_(None))).all())
    all_topics = db.scalars(select(Topic).order_by(Topic.id)).all()
    topics = [t for t in all_topics if t.archived_at is None and t.subject_id in active_subject_ids]
    active_topic_ids = {t.id for t in topics}
    # Questões de matérias/assuntos arquivados também saem da pilha, sem perder histórico.
    questions = db.scalars(select(Question).order_by(Question.id)).all()
    active_questions = [q for q in questions if q.archived_at is None
                        and (q.subject_id is None or q.subject_id in active_subject_ids)
                        and (q.topic_id is None or q.topic_id in active_topic_ids)]
    topic_reviews = db.scalars(select(TopicReview).order_by(TopicReview.created_at, TopicReview.id)).all()
    attempts = db.scalars(select(QuestionAttempt).order_by(QuestionAttempt.created_at, QuestionAttempt.id)).all()
    new_content = db.scalars(select(NewContentLog).order_by(NewContentLog.created_at, NewContentLog.id)).all()

    by_topic: dict[int, list[TopicReview]] = defaultdict(list)
    by_question: dict[int, list[QuestionAttempt]] = defaultdict(list)
    question_by_topic: dict[int, list[QuestionAttempt]] = defaultdict(list)
    latest_study: dict[int, datetime] = {}
    for review in topic_reviews:
        by_topic[review.topic_id].append(review)
    topic_for_question = {q.id: q.topic_id for q in questions}
    for attempt in attempts:
        by_question[attempt.question_id].append(attempt)
        topic_id = topic_for_question.get(attempt.question_id)
        if topic_id is not None:
            question_by_topic[topic_id].append(attempt)
    for content in new_content:
        latest_study[content.topic_id] = content.created_at

    topic_queue = []
    for topic in topics:
        history = by_topic[topic.id]
        if exclude_session_id is not None and any(r.session_id == exclude_session_id for r in history):
            continue
        last = history[-1] if history else None
        reference = last.created_at if last else latest_study.get(topic.id)
        days = elapsed_days(reference, now)
        interval = topic_interval(history)
        ratio = 1.0 if days is None else days / interval
        due = ratio >= 1.0
        # Sem primeira nota, assunto fica disponível, mas pode estar em espera
        # de 1 dia se a estudante marcou que acabou de vê-lo na aula.
        recall_difficulty = (4 - last.grade) / 4 if last else 0.50
        perceived = ((last.difficulty - 1) / 2) if last and last.difficulty else recall_difficulty
        difficulty = 0.78 * recall_difficulty + 0.22 * perceived
        gaps = sum(r.grade <= 2 or getattr(r, 'critical_gap', False) for r in history) / len(history) if history else 0.40
        overdue = min(1, ratio / 3)
        # A frequência histórica ajuda, mas um tópico ainda não visto ganha
        # bônus de cobertura; repetição de um tópico nunca apaga outros.
        coverage = 0.05 / (1 + len(history))
        gap_bonus = 0.12 if last and last.critical_gap else 0
        priority = min(1.0, 0.33*difficulty + 0.30*overdue + 0.23*gaps +
                       0.09*topic.importance/5 + coverage + gap_bonus)
        mastered = is_topic_mastered(history, question_by_topic[topic.id])
        if not history and reference is None:
            reason = 'Ainda não estudado — disponível para começar'
        elif not history:
            reason = 'Primeira revisão após a aula' if due else 'Primeira revisão programada'
        elif last and last.critical_gap:
            reason = 'Lacuna conceitual — reforçar a explicação'
        elif due:
            reason = 'Revisão vencida — memória precisa de reforço'
        elif mastered:
            reason = 'Domínio em manutenção espaçada'
        else:
            reason = 'Manutenção programada'
        next_due = (aware(reference) + timedelta(days=interval)).isoformat() if reference else None
        topic_queue.append({
            'id':topic.id, 'subject_id':topic.subject_id,'code':topic.code,'title':topic.title,
            'grade':last.grade if last else None,'difficulty':last.difficulty if last else None,
            'critical_gap':bool(last.critical_gap) if last else False,
            'attempts':len(history),'days_since':round(days,1) if days is not None else None,
            'interval_days':interval,'due':due,'mastered':mastered,'priority':round(priority,4),
            'next_due_at':next_due,'reason':reason,
        })

    topic_subjects = {t.id:t.subject_id for t in topics}
    question_queue = []
    for q in active_questions:
        history = by_question[q.id]
        if exclude_session_id is not None and any(r.session_id == exclude_session_id for r in history):
            continue
        last = history[-1] if history else None
        days = elapsed_days(last.created_at, now) if last else None
        interval = question_interval(history)
        ratio = 1.0 if days is None else days / interval
        due = ratio >= 1.0
        correct = sum(int(r.is_correct) for r in history)
        errors = len(history) - correct
        # Acerto chutado e acerto incerto valem menos para estimar domínio.
        effective_correct = sum((1 if r.confidence in (3, None) else (0.65 if r.confidence == 2 else 0.25))
                                for r in history if r.is_correct)
        smoothed_success = (effective_correct + 1) / (len(history) + 2)
        wrong_rate = errors / len(history) if history else 0.5
        repeated_errors = sum(not r.is_correct for r in history[-3:]) >= 2
        uncertainty = 2 / (len(history) + 2)
        overdue = min(1, ratio / 3)
        # A pilha considera necessidade de reforço, incerteza, tempo sem rever
        # e cobertura de todo o caderno. A prioridade muda a cada avaliação.
        priority = min(1.0, 0.36*(1-smoothed_success) + 0.19*wrong_rate +
                       0.29*overdue + 0.09*uncertainty +
                       (0.12 if repeated_errors else 0.0) + 0.07/(1+len(history)))
        # Somente sugere arquivar após acertos seguros, repetidos e espaçados.
        # Jamais arquiva automaticamente; a decisão é da estudante.
        recent = history[-4:]
        archive_suggested = (
            len(history) >= 6 and len(recent) == 4 and
            all(r.is_correct and r.confidence == 3 for r in recent) and
            correct / len(history) >= 0.80 and
            (elapsed_days(recent[0].created_at, aware(recent[-1].created_at)) or 0) >= 14
        )
        if archive_suggested:
            reason = 'Questão dominada — considere retirá-la da pilha'
        else:
            reason = None
        if reason is None and repeated_errors:
            reason = 'Erros recorrentes — revisar o conceito'
        elif reason is None and last and last.is_correct and last.confidence == 1:
            reason = 'Acerto com chute — não consolidado'
        elif reason is None and not history:
            reason = 'Questão ainda não reavaliada'
        elif reason is None and due:
            reason = 'Retomar questão para reforçar a memória'
        elif reason is None:
            reason = 'Manutenção espaçada'
        next_due = (aware(last.created_at)+timedelta(days=interval)).isoformat() if last else None
        question_queue.append({
            'id':q.id,'subject_id':q.subject_id or topic_subjects.get(q.topic_id),
            'topic_id':q.topic_id,'url':q.url,'statement':q.statement,
            'attempts':len(history),'correct':correct,'errors':errors,
            'last_correct':last.is_correct if last else None,
            'last_confidence':last.confidence if last else None,
            'days_since':round(days,1) if days is not None else None,
            'interval_days':interval,'due':due,'priority':round(priority,4),
            'next_due_at':next_due,'reason':reason,
            'archive_suggested':archive_suggested,
            'archive_reason':('Últimos 4 acertos com segurança, em revisões espaçadas, e pelo menos 80% de acerto no histórico.' if archive_suggested else None),
        })
    # A prioridade é global e contínua: sem primeiro cortar por 'vencidos'
    # ou por dia, permitindo equilibrar revisões e cobertura do edital.
    topic_queue.sort(key=lambda x:(-x['priority'],x['attempts'],x['id']))
    question_queue.sort(key=lambda x:(-x['priority'],x['attempts'],x['id']))
    visible_topics = topic_queue if topic_minutes is None else topic_queue[:topic_minutes//10]
    visible_questions = question_queue if question_minutes is None else question_queue[:question_minutes//5]
    return {
        'topics':visible_topics,'questions':visible_questions,
        'topic_minutes':topic_minutes,'question_minutes':question_minutes,
        'total_topics':len(topics),'total_questions':len(active_questions),
        'archived_questions':len(questions)-len(active_questions),
        'due_topics':sum(x['due'] for x in topic_queue),
        'due_questions':sum(x['due'] for x in question_queue),
        'generated_at':now.isoformat(),
        'note':'Sem tempo obrigatório. Somente respostas registradas são avaliadas; refresh nunca reinicia o histórico.',
    }
