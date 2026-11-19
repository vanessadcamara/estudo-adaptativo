"""Revisão adaptativa com filas independentes por matéria e prazos indicativos.

Fórmula exclusiva dos Cards: P = 0,35D + 0,30T + 0,25E + 0,10I,
com D, T, E e I sempre entre 0 e 100. A manutenção vencida recebe preferência flexível dentro da matéria.
Não é obrigação diária e não impede alternância entre sessões.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import exp, sqrt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NewContentLog, Question, QuestionAttempt, Topic, TopicReview, Subject
from app.assessment import qualifies_as_spaced_success
from app.statistical_retention import profiles_for_queue, item_estimate, blend_interval


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def elapsed_days(then: datetime | None, now: datetime) -> float | None:
    return max(0.0, (aware(now) - aware(then)).total_seconds() / 86400) if then else None


def grade4_streak(records: list[TopicReview]) -> int:
    count = 0
    for record in reversed(records):
        if record.grade != 4 or bool(getattr(record, 'critical_gap', False)):
            break
        count += 1
    return count


def spaced_recoveries(records: list[TopicReview]) -> bool:
    """Três notas 4 em datas distintas, intervalos crescentes e último >= 14 dias."""
    if grade4_streak(records) < 3:
        return False
    # O intervalo cronológico é avaliado nas 3 últimas recuperações consecutivas.
    a, b, c = records[-3:]
    first = elapsed_days(a.created_at, aware(b.created_at)) or 0.0
    second = elapsed_days(b.created_at, aware(c.created_at)) or 0.0
    return first >= 1.0 and second >= 14.0 and second > first


def topic_interval(records: list[TopicReview]) -> int:
    """Intervalo de manutenção individual (1 a 60 dias)."""
    if not records:
        return 1
    last = records[-1]
    if bool(getattr(last, 'critical_gap', False)):
        return 1
    if last.grade <= 2:
        base = (1, 2, 4)[last.grade]
    elif last.grade == 3:
        base = 7
    elif spaced_recoveries(records):
        base = 60
    else:
        base = 30 if grade4_streak(records) >= 2 else 14
    if getattr(last, 'difficulty', None) == 3:
        base = (base + 1) // 2
    # A recuperação recente ainda pesa: uma nota boa após falhas repetidas
    # precisa de mais evidência antes de recuperar um intervalo longo.
    if len(records) > 1 and last.grade >= 3:
        recent_lapses = sum(r.grade <= 2 or bool(getattr(r, 'critical_gap', False))
                            for r in records[-4:-1])
        if recent_lapses:
            base = round(base * max(0.5, 1 - 0.18 * recent_lapses))
    return min(60, max(1, base))


def question_interval(records: list[QuestionAttempt]) -> int:
    """Acerto inseguro não autoriza espaçamento longo."""
    if not records or not records[-1].is_correct:
        return 1
    confidence = getattr(records[-1], 'confidence', None)
    if confidence == 1:
        return 1
    if confidence == 2:
        return 2
    streak = 0
    for record in reversed(records):
        if not record.is_correct or getattr(record, 'confidence', None) in (1, 2):
            break
        streak += 1
    base = (3, 7, 14, 30, 60)[min(max(0, streak - 1), 4)]
    # Erros anteriores limitam o salto logo após um acerto seguro isolado.
    if len(records) > 1:
        recent_errors = sum(not r.is_correct for r in records[-4:-1])
        if recent_errors:
            base = round(base * max(0.5, 1 - 0.2 * recent_errors))
    return min(60, max(1, base))


def retention_observations(records: list[Any], interval_fn, successful) -> list[dict[str, Any]]:
    """Recuperações observadas após >= 1 dia; nunca inclui estudo inicial.

    O intervalo previsto é computado APENAS com dados disponíveis antes da
    resposta atual, evitando usar informações do futuro na auditoria.
    """
    observations = []
    for index in range(1, len(records)):
        previous, current = records[index - 1], records[index]
        days = elapsed_days(previous.created_at, aware(current.created_at))
        if days is None or days < 1:
            continue
        scheduled = interval_fn(records[:index])
        observations.append({
            'actual_days': round(days, 3),
            'previously_recommended_days': scheduled,
            'ratio_to_recommendation': days / max(1, scheduled),
            'success': bool(successful(current)),
            'structured': (getattr(current, 'recall_level', None) is not None
                           if isinstance(current, TopicReview) else True),
        })
    return observations


def wilson_lower(successes: int, total: int) -> float:
    """Limite inferior de Wilson (95%); não corrige vieses de autoavaliação."""
    if not total:
        return 0.0
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z*z/total
    return (p + z*z/(2*total) - z*sqrt(p*(1-p)/total + z*z/(4*total*total))) / denominator


def retention_interval_validation(records: list[Any], baseline: int, interval_fn,
                                  successful) -> dict[str, Any]:
    """Auditoria legível do intervalo real, sem alegar validação científica.

    Compara apenas recuperações aproximadamente similares ao prazo agora
    proposto; sucessos muito mais curtos não justificam ampliar o intervalo.
    """
    observations = retention_observations(records, interval_fn, successful)
    comparable = [o for o in observations[-30:] if 0.6 * baseline <= o['actual_days'] <= 1.6 * baseline]
    successes = sum(o['success'] for o in comparable)
    total = len(comparable)
    by_days = []
    for label, low, high in [('1–3', 1, 4), ('4–7', 4, 8), ('8–14', 8, 15),
                             ('15–30', 15, 31), ('31+', 31, float('inf'))]:
        entries = [o for o in observations if low <= o['actual_days'] < high]
        by_days.append({'range': label, 'samples': len(entries),
                        'successes': sum(o['success'] for o in entries),
                        'success_percent': round(100 * sum(o['success'] for o in entries) / len(entries), 1)
                        if entries else None})
    lower = wilson_lower(successes, total)
    structured_count = sum(o['structured'] for o in comparable)
    growth_ready = (total >= 8 and structured_count >= 8 and successes / total >= 0.85
                    and lower >= 0.70)
    return {
        'spaced_samples': len(observations),
        'structured_spaced_samples': sum(o['structured'] for o in observations),
        'comparable_samples': total,
        'comparable_successes': successes,
        'comparable_structured_samples': structured_count,
        'comparable_success_percent': round(100 * successes / total, 1) if total else None,
        'comparable_wilson_lower_percent': round(100 * lower, 1) if total else None,
        'evidence_sufficient_for_growth': growth_ready,
        'by_actual_interval': by_days,
        'note': 'Autoavaliação e amostra selecionada; não é probabilidade validada.',
    }


def observed_retention_interval(records: list[Any], baseline: int, successful,
                                subject_histories: list[list[Any]] | None = None) -> int:
    """Calibração conservadora por tempo *real*, sem extrapolar de intervalos curtos.

    Ampliação de até 25% exige >= 8 recuperações em intervalos comparáveis,
    com limite inferior de Wilson >= 70%. A condição é uma salvaguarda
    heurística, não um teste estatístico de memória individual.
    Insucessos no prazo ou antes dele podem encurtar o próximo intervalo.
    Informações agregadas da matéria só apoiam reduções, nunca justificam
    ampliar individualmente um assunto com poucas revisões próprias.
    """
    if not records:
        return baseline
    interval_fn = topic_interval if isinstance(records[0], TopicReview) else question_interval
    local = retention_observations(records, interval_fn, successful)
    using_local = len(local) >= 6
    if using_local:
        evidence = local[-30:]
        weight = min(1.0, len(evidence) / 12)
    else:
        pooled = [ob for history in (subject_histories or [])
                  for ob in retention_observations(history, interval_fn, successful)]
        if len(pooled) < 12:
            return baseline
        evidence = pooled[-100:]
        weight = min(0.5, len(evidence) / 60)

    # A falha antes/próximo ao prazo sugere que a previsão foi otimista.
    # Falhas muito depois do vencimento não provam que o prazo estava errado.
    early_failures = sum(not o['success'] and o['ratio_to_recommendation'] <= 1.5
                         for o in evidence)
    # Um sucesso em três dias não comprova retenção por trinta.
    comparable = [o for o in (local[-30:] if using_local else [])
                  if 0.6 * baseline <= o['actual_days'] <= 1.6 * baseline]
    successes = sum(o['success'] for o in comparable)
    # Para ampliar tópicos, evidência de questionário estruturado é obrigatória;
    # registros antigos continuam úteis para redução e leitura histórica.
    structured_comparable = (len([o for o in comparable if o['structured']])
                             if isinstance(records[0], TopicReview) else len(comparable))
    growth_validated = (len(comparable) >= 8 and structured_comparable >= 8
                        and successes / len(comparable) >= 0.85
                        and wilson_lower(successes, len(comparable)) >= 0.70)

    if early_failures >= 3:
        net = max(0, early_failures - sum(o['success'] and o['ratio_to_recommendation'] >= 0.85
                                           for o in evidence))
        if net > 0:
            factor = 1 - 0.25 * weight * net / max(1, len(evidence))
            return max(1, min(60, max(round(baseline * 0.75 + 0.000001), round(baseline * factor))))

    if growth_validated:
        factor = 1 + 0.25 * weight * (successes / len(comparable))
        return max(1, min(60, round(baseline * factor)))
    return baseline


def forgetting_risk(days: float | None, interval: int, baseline: float) -> float | None:
    """Estimativa heurística 0–100, não é probabilidade calibrada nem um ML.

    Baseline deriva do desempenho observado; a componente temporal cresce
    continuamente e alcança ~35% adicional do risco restante no vencimento.
    Não atribuímos risco inventado a um item sem histórico.
    """
    if days is None:
        return None
    baseline = max(0.0, min(0.95, baseline))
    remaining = (1 - baseline) * exp(-0.43 * max(0.0, days) / max(1, interval))
    return round(100 * (1 - remaining), 1)


def topic_forgetting_risk(records: list[TopicReview], days: float | None,
                          interval: int) -> float | None:
    if not records:
        return None
    last = records[-1]
    recent = records[-4:]
    lapses = sum(r.grade <= 2 or bool(getattr(r, 'critical_gap', False)) for r in recent)
    baseline = 0.05 + 0.10 * (4 - last.grade) + 0.08 * lapses / len(recent)
    if bool(getattr(last, 'critical_gap', False)):
        baseline += 0.12
    if getattr(last, 'difficulty', None) == 3:
        baseline += 0.08
    return forgetting_risk(days, interval, baseline)


def question_forgetting_risk(records: list[QuestionAttempt], days: float | None,
                             interval: int) -> float | None:
    if not records:
        return None
    last = records[-1]
    if not last.is_correct:
        baseline = 0.62
    else:
        baseline = {1: 0.48, 2: 0.26, 3: 0.07, None: 0.22}.get(last.confidence, 0.22)
    recent = records[-4:]
    baseline += 0.16 * sum(not r.is_correct for r in recent) / len(recent)
    return forgetting_risk(days, interval, baseline)


def risk_level(risk: float | None) -> str:
    if risk is None:
        return 'sem_dados'
    return 'alto' if risk >= 65 else 'moderado' if risk >= 35 else 'baixo'



def empirical_risk_adjustment(histories: list[list[Any]], interval_fn, risk_fn,
                              unsuccessful, now: datetime) -> tuple[float, int]:
    """Correção retrospectiva conservadora, APENAS por matéria e por tipo.

    Compara o risco pré-revisão com o resultado da revisão seguinte. Não é
    calibração probabilística formal: amostras são pequenas e selecionadas.
    Não modifica o banco de dados, nunca cruza matérias ou Cards/Questões.
    """
    deltas: list[float] = []
    for events in histories:
        for index in range(1, len(events)):
            prior = events[:index]
            at = aware(events[index].created_at)
            if at <= aware(prior[-1].created_at) or at > now:
                continue
            days = elapsed_days(prior[-1].created_at, at)
            forecast = risk_fn(prior, days, interval_fn(prior))
            if forecast is not None:
                deltas.append((1.0 if unsuccessful(events[index]) else 0.0) - forecast / 100.0)
    samples = len(deltas)
    if samples < 12:
        return 0.0, samples
    # Até 12 pontos percentuais, exigindo muitas observações para ganhar peso.
    correction = (sum(deltas) / samples) * min(0.5, samples / (samples + 20))
    return max(-0.12, min(0.12, correction)), samples


def risk_calibration_audit(histories: list[list[Any]], interval_fn, risk_fn,
                           unsuccessful, now: datetime) -> dict[str, Any]:
    """Audita previsões feitas com o passado contra cada revisão seguinte.

    Brier 0–1 só é publicado com 20 eventos; amostra selecionada e heurística.
    Não é avaliação em amostra aleatória nem probabilidade validada.
    """
    pairs: list[tuple[float, int]] = []
    for events in histories:
        for index in range(1, len(events)):
            prior = events[:index]
            at = aware(events[index].created_at)
            if at <= aware(prior[-1].created_at) or at > now:
                continue
            forecast = risk_fn(prior, elapsed_days(prior[-1].created_at, at), interval_fn(prior))
            if forecast is not None:
                pairs.append((forecast / 100, int(bool(unsuccessful(events[index])))))
    if len(pairs) < 20:
        return {'samples': len(pairs), 'brier': None, 'sufficient': False}
    return {'samples': len(pairs),
            'brier': round(sum((p-y)**2 for p,y in pairs) / len(pairs), 4),
            'sufficient': True}


def adjusted_risk(raw_risk: float | None, correction: float) -> float | None:
    return None if raw_risk is None else round(max(0.0, min(100.0, raw_risk + 100 * correction)), 1)


def ranking_score(priority: float, risk: float | None) -> tuple[float, float]:
    """Fórmula-base intacta; risco adiciona no máximo 8 pontos à ordenação."""
    bonus = round(0.08 * risk, 2) if risk is not None else 0.0
    return round(min(100.0, priority + bonus), 2), bonus


def topic_opportunity_bonus(evidence: dict[str, Any]) -> float:
    """Bônus limitado 0–6 baseado em falhas observadas por assunto.

    Sem evidências = zero bônus; vínculo da questão sem tentativas não pontua.
    Amostras pequenas têm peso reduzido. Não utiliza pesos do edital nem dados
    de inéditas agregadas por matéria.
    """
    n = evidence['distinct_questions']
    rate = evidence['question_accuracy_percent']
    if not n or rate is None:
        return 0.0
    gap = max(0.0, 90.0 - rate) / 90.0
    return round(6.0 * gap * min(1.0, n / 5.0), 2)


def semi_novel_progress(questions: list[Question], attempts_by_question: dict[int, list[QuestionAttempt]],
                        now: datetime) -> dict[str, Any]:
    """Retenção na amostra que JÁ foi errada no site externo.

    Só conta a ÚLTIMA reavaliação elegível por link distinto, separada da
    tentativa anterior por ao menos sete dias. Primeiro erro externo NÃO é
    uma tentativa do app, e itens ainda não reavaliados não viram fracassos.
    """
    verified: list[tuple[int, datetime, bool]] = []
    first_pass = 0
    for question in questions:
        events = [a for a in attempts_by_question[question.id] if aware(a.created_at) <= now]
        if events:
            first_pass += 1
        last_spaced = None
        if len(events) >= 2:
            gap = elapsed_days(events[-2].created_at, aware(events[-1].created_at)) or 0.0
            if gap >= 7:
                last_spaced = events[-1]
        if last_spaced is not None:
            verified.append((question.id, aware(last_spaced.created_at),
                             bool(last_spaced.is_correct and last_spaced.confidence == 3)))
    count = len(verified)
    secure = sum(ok for _, _, ok in verified)
    recent = [(at, ok) for _, at, ok in verified if (now-at).days < 30]
    previous = [(at, ok) for _, at, ok in verified if 30 <= (now-at).days < 60]
    recent_rate = 100*sum(ok for _,ok in recent)/len(recent) if recent else None
    previous_rate = 100*sum(ok for _,ok in previous)/len(previous) if previous else None
    trend = round(recent_rate-previous_rate,1) if len(recent)>=5 and len(previous)>=5 else None
    return {
        'registered': len(questions), 'reviewed_in_app': first_pass,
        'spaced_distinct': count, 'spaced_secure': secure,
        'spaced_secure_percent': round(100*secure/count,1) if count else None,
        'recent_30d_count': len(recent),
        'recent_30d_percent': round(recent_rate,1) if recent_rate is not None else None,
        'previous_30d_count': len(previous),
        'previous_30d_percent': round(previous_rate,1) if previous_rate is not None else None,
        'trend_pp': trend, 'target_percent': 90,
        'sufficient_sample': count >= 10,
        'interpretation': 'Amostra enviesada: somente questões erradas previamente no site; não estima nota da prova.',
    }

def pending_topic_gap(records: list[TopicReview]) -> bool:
    """Uma lacuna crítica só é resolvida por nova explicação segura sem lacunas."""
    pending = False
    for record in records:
        if getattr(record, 'critical_gap', False):
            pending = True
        elif pending and record.grade >= 3 and getattr(record, 'explained_without_consulting', False):
            pending = False
    return pending


def pending_concept_errors(attempts: list[QuestionAttempt]) -> int:
    """Erros conceituais vinculados deixam de ser pendentes após acerto seguro posterior."""
    pending: dict[int, bool] = {}
    for attempt in attempts:
        if not attempt.is_correct and getattr(attempt, 'error_type', None) == 'concept':
            pending[attempt.question_id] = True
        elif attempt.is_correct and getattr(attempt, 'confidence', None) == 3:
            pending[attempt.question_id] = False
    return sum(bool(value) for value in pending.values())


def mastery_evidence(records: list[TopicReview], attempts: list[QuestionAttempt]) -> dict[str, Any]:
    """Portões verificáveis para afirmar domínio — nunca inferir a evidência ausente."""
    last = records[-1] if records else None
    streak_ok = grade4_streak(records) >= 3
    spaced_ok = spaced_recoveries(records)
    # Usa apenas o último resultado de cada questão diferente, evitando que
    # repetir o mesmo link infle artificialmente a amostra de acertos.
    last_by_question: dict[int, QuestionAttempt] = {}
    for attempt in attempts:
        last_by_question[attempt.question_id] = attempt
    distinct_count = len(last_by_question)
    correct_count = sum(int(r.is_correct and getattr(r, 'confidence', None) in (2, 3))
                        for r in last_by_question.values())
    rate = correct_count / distinct_count if distinct_count else 0.0
    sample_ok = distinct_count >= 5 and len(attempts) >= 8 and rate >= 0.90
    pending_concepts = pending_concept_errors(attempts)
    critical_clear = not pending_topic_gap(records) and pending_concepts == 0
    explained = bool(last and getattr(last, 'explained_without_consulting', False) and last.grade == 4)
    # Diversidade e ineditismo não são dedutíveis dos links sem acessar o conteúdo.
    # Solicitamos confirmação explícita; não fingimos classificá-los automaticamente.
    novel_applied = bool(last and getattr(last, 'applied_to_new_questions', False))
    checks = {
        'three_grade_fours': streak_ok,
        'spaced_recoveries': spaced_ok,
        'varied_questions_90_percent': sample_ok,
        'no_critical_gaps': critical_clear,
        'explained_without_consulting': explained,
        'applied_to_new_questions': novel_applied,
    }
    return {
        **checks,
        'mastered': all(checks.values()),
        'question_accuracy_percent': round(100 * rate, 1) if distinct_count else None,
        'distinct_questions': distinct_count,
        'total_question_attempts': len(attempts),
        'pending_concept_errors': pending_concepts,
        'grade_four_streak': grade4_streak(records),
    }


def is_topic_mastered(records: list[TopicReview], attempts: list[QuestionAttempt]) -> bool:
    return mastery_evidence(records, attempts)['mastered']


def topic_state(records: list[TopicReview], evidence: dict[str, Any]) -> str:
    if evidence['mastered']:
        return 'dominado'
    if not records:
        return 'em_aprendizagem'
    last = records[-1]
    if last.grade <= 2 or not evidence['no_critical_gaps']:
        return 'em_aprendizagem'
    return 'em_consolidacao'


def topic_priority_components(topic: Topic, history: list[TopicReview], days: float | None, interval: int) -> dict[str, float]:
    """Componentes normalizados 0–100, nenhum bônus externo à fórmula."""
    last = history[-1] if history else None
    recall_difficulty = (4 - last.grade) * 25.0 if last else 50.0
    perceived = (last.difficulty - 1) * 50.0 if last and last.difficulty else recall_difficulty
    difficulty = 0.78 * recall_difficulty + 0.22 * perceived
    temporal = min(100.0, (days / interval) * 100.0) if days is not None else 0.0
    forget_count = sum(r.grade <= 2 or bool(getattr(r, 'critical_gap', False)) for r in history)
    forgetfulness = 100 * forget_count / len(history) if history else 50.0
    importance = (topic.importance - 1) * 25.0  # escala cadastrada 1–5
    return {k: round(max(0.0, min(100.0, v)), 2) for k, v in {
        'D': difficulty, 'T': temporal, 'E': forgetfulness, 'I': importance
    }.items()}


def build_queue(db: Session, now: datetime | None = None, exclude_session_id: int | None = None,
                topic_minutes: int | None = None, question_minutes: int | None = None,
                subject_id: int | None = None) -> dict[str, Any]:
    """Fila scoped da matéria selecionada. None = agregação legada sem metas.

    O frontend sempre informa subject_id; 0 representa questões antigas sem
    matéria, em uma fila isolada. Nunca usamos atrasos para escolher matéria.
    Os parâmetros de minutos são somente compatibilidade com clientes antigos.
    """
    for value in (topic_minutes, question_minutes):
        if value is not None and not (0 <= value <= 180):
            raise ValueError('Tempo de fila inválido.')
    now = aware(now or datetime.now(timezone.utc))
    active_subject_ids = set(db.scalars(select(Subject.id).where(Subject.archived_at.is_(None))).all())
    all_topics = db.scalars(select(Topic).order_by(Topic.id)).all()
    topic_subject_lookup = {t.id: t.subject_id for t in all_topics}
    topics = [t for t in all_topics if t.archived_at is None and t.subject_id in active_subject_ids
              and (subject_id is None or t.subject_id == subject_id)]
    active_topic_ids = {t.id for t in topics}
    questions = db.scalars(select(Question).order_by(Question.id)).all()
    active_questions = [q for q in questions if q.archived_at is None
                        and (q.subject_id is None or q.subject_id in active_subject_ids)
                        and (q.topic_id is None or q.topic_id in active_topic_ids)
                        and (subject_id is None or (q.subject_id or topic_subject_lookup.get(q.topic_id) or 0) == subject_id)]
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

    fsrs_profiles = profiles_for_queue(db)

    # Calibração experimental sempre restrita à própria matéria. Nunca usa
    # históricos de Português para alterar prioridades de Matemática.
    topic_subject_histories: dict[int, list[list[TopicReview]]] = defaultdict(list)
    question_subject_histories: dict[int, list[list[QuestionAttempt]]] = defaultdict(list)
    for topic in topics:
        topic_subject_histories[topic.subject_id].append(by_topic[topic.id])
    for q in active_questions:
        scope_id = q.subject_id or topic_subject_lookup.get(q.topic_id) or 0
        question_subject_histories[scope_id].append(by_question[q.id])
    topic_adjustments = {scope: empirical_risk_adjustment(
        rows, topic_interval, topic_forgetting_risk,
        lambda r: r.grade <= 2 or bool(getattr(r, 'critical_gap', False)), now)
        for scope, rows in topic_subject_histories.items()}
    question_adjustments = {scope: empirical_risk_adjustment(
        rows, question_interval, question_forgetting_risk,
        lambda r: not r.is_correct or r.confidence != 3, now)
        for scope, rows in question_subject_histories.items()}

    # Auditoria não exibida como promessa de probabilidade individual.
    topic_audits = {scope: risk_calibration_audit(
        rows, topic_interval, topic_forgetting_risk,
        lambda r: r.grade <= 2 or bool(getattr(r, 'critical_gap', False)), now)
        for scope, rows in topic_subject_histories.items()}
    question_audits = {scope: risk_calibration_audit(
        rows, question_interval, question_forgetting_risk,
        lambda r: not r.is_correct or r.confidence != 3, now)
        for scope, rows in question_subject_histories.items()}

    topic_queue = []
    for topic in topics:
        history = by_topic[topic.id]
        if exclude_session_id is not None and (
            any(r.session_id == exclude_session_id for r in history) or
            any(log.session_id == exclude_session_id and log.topic_id == topic.id
                for log in new_content)
        ):
            continue
        last = history[-1] if history else None
        reference = last.created_at if last else latest_study.get(topic.id)
        days = elapsed_days(reference, now)
        evidence = mastery_evidence(history, question_by_topic[topic.id])
        mastered = evidence['mastered']
        # Não alonga um intervalo a 60 dias sem comprovar domínio integral.
        base_interval = topic_interval(history)
        if not mastered:
            base_interval = min(30, base_interval)
        interval = observed_retention_interval(
            history, base_interval,
            qualifies_as_spaced_success,
            topic_subject_histories.get(topic.subject_id))
        if not mastered:
            interval = min(30, interval)
        profile = fsrs_profiles.get(f'topic:{topic.subject_id}')
        optimized = bool(profile and profile.optimizer_active and profile.optimizer_parameters)
        active = bool(optimized or (profile and profile.active))
        estimate = item_estimate(history, 'topic', now,
                                 factor=1.0 if optimized else (profile.factor if active else 1.0),
                                 parameters=profile.optimizer_parameters if optimized else None)
        if estimate is not None:
            interval = blend_interval(interval, estimate['fsrs_interval_days'], active,
                                      maximum=60 if mastered else 30)
        overdue_days = max(0.0, days - interval) if days is not None else 0.0
        correction, calibration_samples = topic_adjustments.get(topic.subject_id, (0.0, 0))
        risk = adjusted_risk(topic_forgetting_risk(history, days, interval), correction)
        if active and estimate is not None:
            risk = round(100 - estimate['expected_recall_percent'], 1)
        maintenance_required = days is not None and days >= interval
        components = topic_priority_components(topic, history, days, interval)
        priority = round(0.35 * components['D'] + 0.30 * components['T'] +
                         0.25 * components['E'] + 0.10 * components['I'], 2)
        recommended_priority, risk_bonus = ranking_score(priority, risk)
        opportunity_bonus = topic_opportunity_bonus(evidence)
        recommended_priority = round(min(100.0, recommended_priority + opportunity_bonus), 2)
        state = topic_state(history, evidence)
        if not history and reference is None:
            reason = 'Assunto novo — primeira avaliação disponível'
        elif not history:
            reason = 'Primeira revisão após estudo inicial' if maintenance_required else 'Primeira revisão programada'
        elif maintenance_required:
            reason = 'Prazo de revisão atingido — prioridade nesta matéria'
        elif not evidence['no_critical_gaps']:
            reason = 'Erro conceitual pendente — reforçar antes de avançar'
        elif mastered:
            reason = 'Domínio comprovado — manutenção espaçada'
        else:
            reason = 'Consolidação e revisões espaçadas'
        next_due = (aware(reference) + timedelta(days=interval)).isoformat() if reference else None
        topic_queue.append({
            'id': topic.id, 'subject_id': topic.subject_id, 'code': topic.code, 'title': topic.title,
            'grade': last.grade if last else None, 'difficulty': last.difficulty if last else None,
            'critical_gap': bool(last.critical_gap) if last else False,
            'attempts': len(history), 'days_since': round(days, 1) if days is not None else None,
            'interval_days': interval, 'base_interval_days': base_interval,
            'interval_adjustment_days': interval - base_interval,
            'retention_model': {
                'stage': ('otimizado' if optimized else profile.stage) if profile else 'observando',
                'source': ('FSRS-6 otimizado (21 parâmetros)' if optimized and estimate else
                           'FSRS calibrado' if active and estimate else 'regras v0.14'),
                'optimizer': profile.optimizer_metrics if optimized and profile else None,
                'active': bool(active and estimate),
                **(estimate or {}),
                'scope': f'topic:{topic.subject_id}',
                'validation': profile.metrics if profile else None,
            },
            'retention_validation': retention_interval_validation(history, base_interval, topic_interval, qualifies_as_spaced_success),
            'due': maintenance_required,
            'maintenance_required': maintenance_required, 'overdue_days': round(overdue_days, 2),
            'forgetting_risk_percent': risk, 'forgetting_risk_level': risk_level(risk),
            'risk_calibration_samples': calibration_samples,
            'risk_calibration_adjustment_pp': round(100 * correction, 2),
            'risk_calibration_audit': topic_audits.get(topic.subject_id),
            'ranking_score': recommended_priority, 'risk_priority_bonus': risk_bonus,
            'opportunity_priority_bonus': opportunity_bonus,
            'mastered': mastered, 'learning_state': state, 'mastery_evidence': evidence,
            'priority': priority, 'priority_components': components,
            'next_due_at': next_due, 'reason': reason,
        })

    topic_subjects = {t.id: t.subject_id for t in topics}
    question_queue = []
    for q in active_questions:
        history = by_question[q.id]
        if exclude_session_id is not None and any(r.session_id == exclude_session_id for r in history):
            continue
        last = history[-1] if history else None
        days = elapsed_days(last.created_at, now) if last else None
        interval = question_interval(history)
        base_interval = interval
        scope_id = q.subject_id or topic_subject_lookup.get(q.topic_id) or 0
        interval = observed_retention_interval(
            history, interval, lambda r: r.is_correct and r.confidence == 3,
            question_subject_histories.get(scope_id))
        profile = fsrs_profiles.get(f'question:{scope_id}')
        optimized = bool(profile and profile.optimizer_active and profile.optimizer_parameters)
        active = bool(optimized or (profile and profile.active))
        estimate = item_estimate(history, 'question', now,
                                 factor=1.0 if optimized else (profile.factor if active else 1.0),
                                 parameters=profile.optimizer_parameters if optimized else None)
        if estimate is not None:
            interval = blend_interval(interval, estimate['fsrs_interval_days'], active)
        correction, calibration_samples = question_adjustments.get(scope_id, (0.0, 0))
        risk = adjusted_risk(question_forgetting_risk(history, days, interval), correction)
        if active and estimate is not None:
            risk = round(100 - estimate['expected_recall_percent'], 1)
        ratio = days / interval if days is not None else 0.0
        maintenance_required = days is not None and days >= interval
        correct = sum(int(r.is_correct) for r in history)
        errors = len(history) - correct
        effective_correct = sum((1 if r.confidence in (3, None) else (0.65 if r.confidence == 2 else 0.25))
                                for r in history if r.is_correct)
        smoothed_success = (effective_correct + 1) / (len(history) + 2)
        wrong_rate = errors / len(history) if history else 0.5
        repeated_errors = sum(not r.is_correct for r in history[-3:]) >= 2
        uncertainty = 2 / (len(history) + 2)
        overdue = min(1, ratio / 3)
        raw_priority = min(1.0, 0.36 * (1 - smoothed_success) + 0.19 * wrong_rate +
                           0.29 * overdue + 0.09 * uncertainty +
                           (0.12 if repeated_errors else 0.0) + 0.07 / (1 + len(history)))
        priority = round(raw_priority * 100, 2)
        recommended_priority, risk_bonus = ranking_score(priority, risk)
        recent = history[-4:]
        archive_suggested = (
            len(history) >= 6 and len(recent) == 4 and
            all(r.is_correct and r.confidence == 3 for r in recent) and
            correct / len(history) >= 0.80 and
            (elapsed_days(recent[0].created_at, aware(recent[-1].created_at)) or 0) >= 14
        )
        if archive_suggested:
            reason = 'Questão dominada — considere arquivá-la'
        elif repeated_errors:
            reason = 'Erros recorrentes — revisar o conceito'
        elif last and last.is_correct and last.confidence == 1:
            reason = 'Acerto com chute — não consolidado'
        elif not history:
            reason = 'Questão ainda não reavaliada'
        elif maintenance_required:
            reason = 'Prazo de revisão atingido — prioridade nesta matéria'
        else:
            reason = 'Manutenção espaçada'
        next_due = (aware(last.created_at) + timedelta(days=interval)).isoformat() if last else None
        question_queue.append({
            'id': q.id, 'subject_id': q.subject_id or topic_subjects.get(q.topic_id),
            'topic_id': q.topic_id, 'url': q.url, 'statement': q.statement,
            'attempts': len(history), 'correct': correct, 'errors': errors,
            'last_correct': last.is_correct if last else None,
            'last_confidence': last.confidence if last else None,
            'days_since': round(days, 1) if days is not None else None,
            'interval_days': interval, 'base_interval_days': base_interval,
            'interval_adjustment_days': interval - base_interval,
            'retention_model': {
                'stage': ('otimizado' if optimized else profile.stage) if profile else 'observando',
                'source': ('FSRS-6 otimizado (21 parâmetros)' if optimized and estimate else
                           'FSRS calibrado' if active and estimate else 'regras v0.14'),
                'optimizer': profile.optimizer_metrics if optimized and profile else None,
                'active': bool(active and estimate),
                **(estimate or {}),
                'scope': f'question:{scope_id}',
                'validation': profile.metrics if profile else None,
            },
            'retention_validation': retention_interval_validation(history, base_interval, question_interval,
                lambda r: r.is_correct and r.confidence == 3),
            'due': maintenance_required,
            'maintenance_required': maintenance_required,
            'forgetting_risk_percent': risk, 'forgetting_risk_level': risk_level(risk),
            'risk_calibration_samples': calibration_samples,
            'risk_calibration_adjustment_pp': round(100 * correction, 2),
            'risk_calibration_audit': question_audits.get(scope_id),
            'ranking_score': recommended_priority, 'risk_priority_bonus': risk_bonus,
            'overdue_days': round(max(0.0, days - interval), 2) if days is not None else 0.0,
            'priority': priority, 'next_due_at': next_due, 'reason': reason,
            'archive_suggested': archive_suggested,
            'archive_reason': ('Últimos 4 acertos seguros, espaçados e pelo menos 80% de acerto no histórico.'
                               if archive_suggested else None),
        })

    # Diversificação por sessões da própria matéria, sem janela de dias corridos.
    # Uma sessão é contada uma vez, mesmo com várias atividades registradas.
    # A sessão em andamento é ignorada até o próximo ciclo, quando informada.
    session_subject_times = defaultdict(dict)
    def register_activity(session_id, subject, created_at):
        if subject is None or session_id == exclude_session_id:
            return
        times = session_subject_times[subject]
        stamp = aware(created_at)
        if stamp <= now and (session_id not in times or stamp > times[session_id]):
            times[session_id] = stamp

    for review in topic_reviews:
        register_activity(review.session_id, topic_subject_lookup.get(review.topic_id), review.created_at)
    question_lookup = {q.id: q for q in questions}
    for attempt in attempts:
        q = question_lookup.get(attempt.question_id)
        if q is not None:
            register_activity(attempt.session_id, q.subject_id or topic_subject_lookup.get(q.topic_id), attempt.created_at)
    for log in new_content:
        register_activity(log.session_id, topic_subject_lookup.get(log.topic_id), log.created_at)

    ordered_sessions = {
        subject: sorted(times.items(), key=lambda pair: (pair[1], pair[0]), reverse=True)
        for subject, times in session_subject_times.items()
    }
    recent_sessions = {subject: {sid for sid, _ in sessions[:3]}
                       for subject, sessions in ordered_sessions.items()}
    long_sessions = {subject: {sid for sid, _ in sessions[:12]}
                     for subject, sessions in ordered_sessions.items()}
    topic_last_reference = {
        t.id: (by_topic[t.id][-1].created_at if by_topic[t.id]
               else latest_study.get(t.id) or t.created_at)
        for t in topics
    }
    question_last_reference = {
        q.id: (by_question[q.id][-1].created_at if by_question[q.id] else q.created_at)
        for q in active_questions
    }


    def diversify(queue, histories, last_references):
        """Ordenação flexível: urgência + risco + cobertura, sem bloqueio por vencimento.

        A penalidade é relativa à frequência nas três sessões anteriores da
        própria matéria. Um item ainda não vencido pode ultrapassar um vencido
        excessivamente repetido, mas a urgência permanece como bônus explícito.
        Nenhum desses ajustes altera a nota de domínio ou os prazos individuais.
        """
        groups = defaultdict(list)
        for item in queue:
            groups[item['subject_id']].append(item)
        for group in groups.values():
            counts = {}
            for item in group:
                selected = recent_sessions.get(item['subject_id'], set())
                counts[item['id']] = len({record.session_id for record in histories[item['id']]
                                          if record.session_id in selected})
            baseline = min(counts.values()) if counts else 0
            for item in group:
                count = counts[item['id']]
                scope = item['subject_id']
                recent_12 = long_sessions.get(scope, set())
                count_12 = len({record.session_id for record in histories[item['id']]
                                if record.session_id in recent_12})
                reference = aware(last_references[item['id']])
                visits_without_review = sum(
                    1 for sid, at in ordered_sessions.get(scope, [])
                    if at > reference and sid not in {
                        record.session_id for record in histories[item['id']]
                    }
                )
                excess = max(0, count - baseline) if len(group) > 1 else 0
                penalty = min(90.0, 30.0 * excess)
                # Long-overdue material cannot be postponed indefinitely by
                # the three-session diversity penalty. Risk strengthens protection.
                days = item['days_since']
                interval = item['interval_days']
                ratio = days / max(1, interval) if days is not None else 0.0
                risk = item['forgetting_risk_percent'] or 0.0
                protection = (max(0.0, min(1.0, (ratio - 1.5) / 1.5))
                              if days is not None and days >= 14 else 0.0)
                if risk >= 80 and ratio >= 1.5 and days is not None and days >= 14:
                    protection = max(protection, 0.5)
                penalty = round(penalty * (1 - protection), 2)
                # Vencimento não é uma barreira absoluta. Atrasos maiores ganham
                # força progressiva, sem eliminar o efeito da diversificação.
                due_bonus = (12.0 + min(8.0, item['overdue_days'] * 0.5)
                             if item['maintenance_required'] else 0.0)
                # Evita antecipar excessivamente a revisão de itens que já têm
                # intervalo longo, a menos que haja uma boa razão para alternar.
                days = item['days_since']
                interval = item['interval_days']
                early_penalty = (12.0 if days is not None and interval > 1
                                 and days < interval * 0.5 else 0.0)
                # Duas escalas: 3 visitas evitam repetição; 12 visitas detectam
                # assuntos negligenciados. Histórico completo mede espera real.
                # Só antecipa itens nunca revisados ou que atingiram manutenção.
                eligible = item['maintenance_required'] or item['attempts'] == 0
                long_bonus = (min(18.0, 3.0 * max(0, visits_without_review - 2))
                              if eligible and count_12 <= 1 else 0.0)
                # Garantia condicional: depois de >=7 visitas elegíveis sem
                # revisão, o item vai ao topo da SUA fila, em rodízio. Não
                # obriga estudar a matéria nem impede pular voluntariamente.
                starvation_protected = bool(eligible and visits_without_review >= 7)
                item['recent_review_count_3_sessions'] = count
                item['recent_review_count_12_sessions'] = count_12
                item['visits_without_review'] = visits_without_review
                item['long_term_fairness_bonus'] = long_bonus
                item['starvation_protected'] = starvation_protected
                item['diversification_penalty'] = penalty
                item['overdue_protection_ratio'] = round(ratio, 2)
                item['overdue_protection_strength'] = round(protection, 2)
                item['diversification_deferred'] = excess >= 2
                item['due_order_bonus'] = round(due_bonus, 2)
                item['early_review_penalty'] = early_penalty
                item['queue_order_score'] = round(
                    item['ranking_score'] + due_bonus + long_bonus - penalty - early_penalty, 2)
        queue.sort(key=lambda x: (-int(x['starvation_protected']),
                                  -x['visits_without_review'] if x['starvation_protected'] else 0,
                                  -x['queue_order_score'], -x['overdue_days'],
                                  x['attempts'], x['id']))

    diversify(topic_queue, by_topic, topic_last_reference)
    diversify(question_queue, by_question, question_last_reference)
    visible_topics = topic_queue if topic_minutes is None else topic_queue[:topic_minutes // 10]
    visible_questions = question_queue if question_minutes is None else question_queue[:question_minutes // 5]
    return {
        'topics': visible_topics, 'questions': visible_questions, 'subject_id': subject_id,
        'semi_novel_progress': semi_novel_progress(active_questions, by_question, now),
        'topic_minutes': topic_minutes, 'question_minutes': question_minutes,
        'total_topics': len(topics), 'total_questions': len(active_questions),
        'archived_questions': len(questions) - len(active_questions),
        'due_topics': sum(x['due'] for x in topic_queue),
        'due_questions': sum(x['due'] for x in question_queue),
        'generated_at': now.isoformat(),
        'note': 'v0.15: FSRS-6 oficial em observação, calibração temporal por matéria e ativação condicionada à validação; não repetição na sessão; alternância de 3 e 12 sessões; proteção de retorno após 7 visitas elegíveis; recuperação avaliada antes de conferir e aplicação opcional; calibração extra de intervalos somente com evidência temporal comparável. Não é validação científica; inéditas permanecem por matéria.', 
    }
