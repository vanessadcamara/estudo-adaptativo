"""v0.15: official FSRS-6 inference, temporal calibration, conservative auto-activation.

The optional full FSRS optimizer (torch) is deliberately NOT run in request handlers.
Only structured, spaced, within-subject observations are eligible for fitting.
Novel question practice is never assigned to individual topics.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (Question, QuestionAttempt, RetentionProfile, RetentionModelRun,
                        Topic, TopicReview, utcnow)

TARGET_RETENTION = 0.90  # not the exam-correctness target
MIN_TRAIN = 180
MIN_VALIDATION = 50
MIN_ITEMS = 18
MIN_FAILURES = 12
MIN_INTERVAL_BINS = 3
# A relatively conservative, bounded scaling of FSRS stability, not a new 21-weight optimizer.
CANDIDATE_FACTORS = (0.65, 0.75, 0.85, 0.92, 1.0, 1.08, 1.17, 1.30, 1.45)


def _fsrs():
    """Lazy import: no torch, no costly model initialization at application startup."""
    try:
        from fsrs import Scheduler, Card, Rating
        return Scheduler, Card, Rating
    except ImportError:
        return None


def _aware(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _days(a: datetime, b: datetime) -> float:
    return max(0.0, (_aware(b) - _aware(a)).total_seconds() / 86400)


def _rating(entry: Any, kind: str, Rating) -> Any | None:
    """Conservative translation; not an Anki flashcard equivalence claim.

    Unknown old-format topic feedback is excluded from statistical calibration.
    Important gaps/assistance are NOT interpreted as independent recall.
    """
    if kind == 'topic':
        if getattr(entry, 'recall_level', None) is None:
            return None
        if (entry.grade <= 2 or bool(entry.critical_gap)
                or (entry.assistance_level is not None and entry.assistance_level >= 2)
                or (entry.accuracy_level is not None and entry.accuracy_level <= 1)):
            return Rating.Again
        if entry.grade == 4 and entry.recall_level == 3 and entry.accuracy_level == 3:
            return Rating.Easy
        return Rating.Good
    if not entry.is_correct or entry.confidence in (1, 2):
        return Rating.Again
    if entry.confidence == 3:
        return Rating.Good
    return None


def _scheduler(parameters: list[float] | None = None):
    api = _fsrs()
    if api is None:
        return None
    Scheduler, _Card, _Rating = api
    # No sub-day steps for this app; no fuzzing, deterministic history replay.
    return Scheduler(**({"parameters": parameters} if parameters is not None else {}),
                     desired_retention=TARGET_RETENTION, learning_steps=(),
                     relearning_steps=(), maximum_interval=60, enable_fuzzing=False)


def _predict_at(scheduler, card, at: datetime, stability_factor: float = 1.0) -> float:
    """Stability adjustment via time scaling, using the official FSRS function."""
    if card.last_review is None:
        return 1.0
    from datetime import timedelta
    seconds = max(0.0, (_aware(at) - _aware(card.last_review)).total_seconds())
    adjusted_at = _aware(card.last_review) + timedelta(seconds=seconds / stability_factor)
    return max(0.0, min(1.0, float(scheduler.get_card_retrievability(
        card, current_datetime=adjusted_at))))


def _interval(scheduler, card, factor: float) -> int:
    """Latest day at which predicted recall remains >= the retention target."""
    if card.last_review is None:
        return 1
    from datetime import timedelta
    prior = _aware(card.last_review)
    result = 1
    for candidate in range(1, 61):
        if _predict_at(scheduler, card, prior + timedelta(days=candidate), factor) >= TARGET_RETENTION:
            result = candidate
        else:
            break
    return result


def _replay(records: list[Any], kind: str, *, now: datetime | None = None,
            parameters: list[float] | None = None):
    api = _fsrs()
    if api is None:
        return [], None, None
    _Scheduler, Card, Rating = api
    scheduler = _scheduler(parameters)
    observations: list[dict[str, Any]] = []
    card = None
    previous = None
    prior_events = []
    for entry in sorted(records, key=lambda r: (_aware(r.created_at), r.id or 0)):
        at = _aware(entry.created_at)
        if now is not None and at > _aware(now):
            continue
        rating = _rating(entry, kind, Rating)
        if rating is None:
            # Do not infer the outcome of legacy / uncertain assessments.
            continue
        if card is None:
            # Explicit id avoids py-fsrs generating it from wall-clock time and sleeping.
            card = Card(card_id=int(entry.topic_id if kind == 'topic' else entry.question_id), due=at)
        elif previous is not None:
            gap = _days(previous, at)
            if gap >= 1.0:
                # Historical v0.14 estimate is computed with only earlier records.
                from app.engine import (topic_interval, topic_forgetting_risk,
                                        question_interval, question_forgetting_risk)
                base_interval = (topic_interval(prior_events) if kind == 'topic'
                                 else question_interval(prior_events))
                base_risk = ((topic_forgetting_risk(prior_events, gap, base_interval)
                              if kind == 'topic'
                              else question_forgetting_risk(prior_events, gap, base_interval)) or 0)
                observations.append({
                    'legacy_probability': 1 - base_risk / 100,
                    'at': at, 'gap_days': gap,
                    'stability_days': float(card.stability) if card.stability else None,
                    'predicted': _predict_at(scheduler, card, at),
                    'outcome': int(rating != Rating.Again),
                })
        # Model update only AFTER forecasting, preventing look-ahead.
        card, _log = scheduler.review_card(card, rating, review_datetime=at)
        previous = at
        prior_events.append(entry)
    return observations, scheduler, card


def item_estimate(records: list[Any], kind: str, now: datetime,
                  *, factor: float = 1.0, parameters: list[float] | None = None) -> dict[str, Any] | None:
    observations, scheduler, card = _replay(records, kind, now=now, parameters=parameters)
    if scheduler is None or card is None or card.last_review is None:
        return None
    return {
        'expected_recall_percent': round(100 * _predict_at(scheduler, card, now, factor), 1),
        'fsrs_interval_days': _interval(scheduler, card, factor),
        'stability_days': round(float(card.stability) * factor, 2) if card.stability else None,
        'difficulty': round(float(card.difficulty), 2) if card.difficulty else None,
        'observed_spaced_samples': len(observations),
    }


def _brier(rows, factor: float = 1.0) -> float | None:
    if not rows:
        return None
    # FSRS-6 retrievability formula, matching the official Python scheduler's
    # whole-day time discretization; the factor dilates elapsed time.
    # R(S) = 0.9 by construction.
    decay = 0.1542
    q = TARGET_RETENTION ** (-1 / decay) - 1
    def forecast(o):
        stability = o['stability_days']
        if not stability or stability <= 0:
            return o['predicted']
        return (1 + q * int(o['gap_days'] / factor) / max(0.001, stability)) ** (-decay)
    return sum((forecast(o) - o['outcome']) ** 2 for o in rows) / len(rows)


def _bins(rows) -> int:
    return len({0 if r['gap_days'] < 4 else 1 if r['gap_days'] < 15 else 2 for r in rows})


def _profile_summary(histories: list[list[Any]], kind: str, now: datetime) -> dict[str, Any]:
    if _fsrs() is None:
        return {'stage': 'indisponivel', 'reason': 'Dependência oficial fsrs não instalada',
                'factor': 1.0, 'active': False, 'samples': 0}
    events = []
    ids = set()
    for index, history in enumerate(histories):
        obs, _sched, _card = _replay(history, kind, now=now)
        if obs:
            ids.add(index)
        events.extend(obs)
    events.sort(key=lambda x: x['at'])
    count = len(events)
    cutoff = max(0, int(count * 0.8))
    training, heldout = events[:cutoff], events[cutoff:]
    default_brier = _brier(heldout)
    legacy_brier = (sum((r['legacy_probability'] - r['outcome'])**2 for r in heldout) / len(heldout)
                    if heldout else None)
    best = (min(CANDIDATE_FACTORS, key=lambda factor: _brier(training, factor))
            if training else 1.0)
    fitted_brier = _brier(heldout, best)
    # Calibrated probability follows the official FSRS-6 forgetting curve.
    def fitted_probability(row):
        decay = 0.1542
        q = TARGET_RETENTION ** (-1/decay) - 1
        return (1 + q * int(row['gap_days'] / best) /
                max(0.001, row['stability_days'] or 1)) ** (-decay)
    expected = sum(fitted_probability(row) for row in heldout) / len(heldout) if heldout else None
    observed = sum(row['outcome'] for row in heldout) / len(heldout) if heldout else None
    sufficient = (len(training) >= MIN_TRAIN and len(heldout) >= MIN_VALIDATION
                  and len(ids) >= MIN_ITEMS and _bins(training) >= MIN_INTERVAL_BINS
                  and sum(1-r['outcome'] for r in training) >= MIN_FAILURES)
    # Do not switch model with worse-than-default holdout performance; the
    # strictly out-of-training validation set guards against overfitting.
    adequate = bool(sufficient and fitted_brier is not None and default_brier is not None
                    and fitted_brier <= default_brier + 0.005
                    and (legacy_brier is None or fitted_brier + 0.005 <= legacy_brier)
                    and abs((observed or 0) - (expected or 0)) <= 0.12)
    stage = ('ativo' if adequate else 'validando' if count >= 50 else 'observando')
    return {
        'stage': stage, 'active': adequate, 'factor': best if adequate else 1.0,
        'candidate_factor': best, 'samples': count, 'training_samples': len(training),
        'validation_samples': len(heldout), 'distinct_items': len(ids),
        'interval_bins': _bins(training), 'training_failures': sum(1-r['outcome'] for r in training),
        'holdout_brier_default': round(default_brier, 5) if default_brier is not None else None,
        'holdout_brier_v14': round(legacy_brier, 5) if legacy_brier is not None else None,
        'holdout_delta_vs_v14': round((legacy_brier - fitted_brier), 5)
            if legacy_brier is not None and fitted_brier is not None else None,
        'holdout_success_count': sum(r['outcome'] for r in heldout),
        'holdout_failure_count': sum(1-r['outcome'] for r in heldout),
        'holdout_by_interval': [
            {'range': name,
             'samples': sum(1 for r in heldout if low <= r['gap_days'] < high),
             'successes': sum(r['outcome'] for r in heldout if low <= r['gap_days'] < high)}
            for name, low, high in (('1–3', 1, 4), ('4–14', 4, 15), ('15+', 15, float('inf')))
        ],
        'holdout_brier_candidate': round(fitted_brier, 5) if fitted_brier is not None else None,
        'holdout_expected_recall_percent': round(expected*100, 1) if expected is not None else None,
        'holdout_observed_recall_percent': round(observed*100, 1) if observed is not None else None,
        'retention_target_percent': 90,
        'method': 'FSRS-6 oficial + calibração de estabilidade no treino + validação temporal',
        'limitations': 'Resultados dos Cards são autoavaliações; questões repetidas podem ter familiaridade. Não prediz nota do concurso.',
    }


def collect_histories(db: Session):
    subjects_for_topics = {t.id: t.subject_id for t in db.scalars(select(Topic)).all()}
    subjects_for_questions = {q.id: q.subject_id or subjects_for_topics.get(q.topic_id) or 0
                              for q in db.scalars(select(Question)).all()}
    groups = defaultdict(lambda: defaultdict(list))
    for entry in db.scalars(select(TopicReview).order_by(TopicReview.created_at, TopicReview.id)):
        subject = subjects_for_topics.get(entry.topic_id)
        if subject is not None:
            groups[f'topic:{subject}'][entry.topic_id].append(entry)
    for entry in db.scalars(select(QuestionAttempt).order_by(QuestionAttempt.created_at, QuestionAttempt.id)):
        subject = subjects_for_questions.get(entry.question_id)
        if subject is not None:
            groups[f'question:{subject}'][entry.question_id].append(entry)
    return groups


def update_profiles(db: Session, *, now: datetime | None = None, session_id: int | None = None) -> list[RetentionProfile]:
    """Automatic lightweight calibration when a session closes; no GPU / torch.

    All rows in scope remain in the DB; only summaries are updated. Full optimizer
    is intentionally not attempted on a free Render web-service request.
    """
    now = now or utcnow()
    stored = {p.scope: p for p in db.scalars(select(RetentionProfile)).all()}
    for scope, items in collect_histories(db).items():
        kind = scope.split(':')[0]
        summary = _profile_summary(list(items.values()), kind, now)
        record = stored.get(scope)
        previous_samples = record.metrics.get('samples', 0) if record and record.metrics else -1
        if record is None:
            record = RetentionProfile(scope=scope)
            db.add(record)
            stored[scope] = record
        record.stage = summary['stage']
        record.factor = summary['factor']
        record.active = summary['active']
        record.metrics = summary
        record.updated_at = now
        if summary.get('samples', 0) != previous_samples:
            db.add(RetentionModelRun(scope=scope, session_id=session_id,
                stage=summary['stage'], active=summary['active'],
                factor=summary['factor'], metrics=summary, created_at=now))
    db.flush()
    return list(stored.values())


def profiles_for_queue(db: Session) -> dict[str, RetentionProfile]:
    return {p.scope: p for p in db.scalars(select(RetentionProfile)).all()}


def blend_interval(legacy: int, fsrs_interval: int, active: bool, *, maximum: int = 60) -> int:
    if not active:
        return legacy
    # Bound each transition; after multiple sessions the bounds can be relaxed
    # by changing policy after observing real data, not by blind extrapolation.
    low = max(1, round(legacy * 0.75))
    high = max(low, round(legacy * 1.25))
    return min(maximum, max(low, min(high, fsrs_interval)))


def public_profile(profile: RetentionProfile) -> dict:
    return {'scope': profile.scope, 'stage': profile.stage, 'active': profile.active,
            'factor': profile.factor, 'updated_at': profile.updated_at.isoformat(),
            'metrics': profile.metrics,
            'optimizer': {
                'status': profile.optimizer_status,
                'active': bool(profile.optimizer_active and profile.optimizer_parameters),
                'parameters_count': len(profile.optimizer_parameters or []),
                'last_run_at': (profile.optimizer_updated_at.isoformat()
                                if profile.optimizer_updated_at else None),
                'metrics': profile.optimizer_metrics,
            }}
