"""Desempenho observado: inéditas agregadas por matéria, evidências por assunto.

NUNCA atribuir acertos agregados a assuntos. O IC Wilson descreve a incerteza
binomial condicional da amostra informada, não sua representatividade da prova.
"""
from collections import defaultdict
from math import sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine import build_queue
from app.models import NovelPractice, Question, QuestionAttempt, Subject

TARGET = 90.0


def wilson_interval(successes: int, total: int) -> dict | None:
    """Faixa de Wilson 95%, ilustrativa para a amostra declarada."""
    if total == 0:
        return None
    z = 1.959963984540054
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = z / denom * sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return {'low': round(100 * max(0, center - margin), 1),
            'high': round(100 * min(1, center + margin), 1)}


def build_performance(db: Session) -> dict:
    active = db.scalars(select(Subject).where(Subject.archived_at.is_(None)).order_by(Subject.name)).all()
    active_ids = {s.id for s in active}
    all_records = db.scalars(select(NovelPractice).where(NovelPractice.archived_at.is_(None))).all()
    grouped = defaultdict(list)
    for item in all_records:
        if item.subject_id in active_ids:
            grouped[item.subject_id].append(item)

    subject_stats = []
    for subject in active:
        rows = grouped[subject.id]
        n = sum(r.total for r in rows)
        k = sum(r.correct for r in rows)
        rate = round(100 * k / n, 1) if n else None
        subject_stats.append({
            'id': subject.id, 'name': subject.name,
            'records': len(rows), 'total': n, 'correct': k,
            'accuracy_percent': rate, 'interval_95': wilson_interval(k, n),
            'observed_target_met': rate is not None and rate >= TARGET,
            'last_date': max((r.practice_date.isoformat() for r in rows), default=None),
        })

    # A fila já contém as evidências de domínio e o isolamento por matéria.
    queue = build_queue(db)
    linked = defaultdict(list)
    for question in db.scalars(select(Question)).all():
        if question.topic_id is not None:
            linked[question.topic_id].append(question.id)
    attempts = defaultdict(list)
    for attempt in db.scalars(select(QuestionAttempt).order_by(QuestionAttempt.created_at, QuestionAttempt.id)).all():
        attempts[attempt.question_id].append(attempt)

    topic_stats = []
    for topic in queue['topics']:
        last_events = [attempts[q][-1] for q in linked[topic['id']] if attempts[q]]
        n = len(last_events)
        k = sum(bool(a.is_correct and a.confidence in (2, 3)) for a in last_events)
        observed = round(100 * k / n, 1) if n else None
        topic_stats.append({
            'id': topic['id'], 'subject_id': topic['subject_id'],
            'code': topic['code'], 'title': topic['title'],
            'learning_state': topic['learning_state'], 'mastered': topic['mastered'],
            'reviews': topic['attempts'], 'distinct_links': n,
            'qualified_correct': k, 'qualified_accuracy_percent': observed,
            'interval_95': wilson_interval(k, n),
            'mastery_evidence': topic['mastery_evidence'],
            'opportunity_priority_bonus': topic.get('opportunity_priority_bonus', 0),
            'forgetting_risk_percent': topic['forgetting_risk_percent'],
        })
    return {
        'target_percent': TARGET,
        'subjects': subject_stats,
        'topics': topic_stats,
        'note': ('Inéditas: apenas resultados agregados declarados por matéria, sem identificação de assuntos. '
                 'Acertos por assunto: somente links distintos vinculados ao Caderno de erros (amostra enviesada). '
                 'Faixas de Wilson 95% não garantem representatividade nem predizem a prova.'),
    }
