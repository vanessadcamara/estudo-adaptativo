"""v0.16: full 21-weight Py-FSRS optimizer, run OUTSIDE web requests.

Temporal holdout protects against training/validation leakage. A new model is
never promoted merely because 512 events exist: it must beat untuned FSRS on
future events, be competitive with the v0.14 baseline, and be calibrated.
No exam accuracy claims or novel-question-to-topic attribution are made here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import RetentionProfile, RetentionModelRun, utcnow
from app import statistical_retention as stat

# Py-FSRS 6.3.2 optimizer internally uses batches of 512 spaced reviews.
# Below that, compute_optimal_parameters() simply returns default parameters.
MIN_OPTIMIZER_SPACED_TRAIN = 512
MIN_HOLDOUT_SPACED = 100
MIN_DISTINCT_TRAIN_ITEMS = 25
MIN_DISTINCT_HOLDOUT_ITEMS = 12
MIN_TRAIN_FAILURES = 25
MIN_HOLDOUT_FAILURES = 8
MIN_INTERVAL_BINS = 3
MAX_HOLDOUT_BRIER_REGRESSION_V14 = 0.005
MIN_IMPROVEMENT_OVER_DEFAULT = 0.005
MAX_CALIBRATION_ERROR = 0.10


def _events_for_scope(histories: dict[int, list[Any]], kind: str, now: datetime):
    """Eligible *spaced* outcomes; each forecast is from the state BEFORE its review."""
    events = []
    for key, history in histories.items():
        observations, _sch, _card = stat._replay(history, kind, now=now)
        events.extend([(o['at'], key, o) for o in observations])
    return sorted(events, key=lambda r: (r[0], r[1]))


def _fingerprint(histories: dict[int, list[Any]], now: datetime) -> dict:
    eligible = []
    for history in histories.values():
        eligible += [(r.created_at, r.id) for r in history if stat._aware(r.created_at) <= stat._aware(now)]
    return {'total_events': len(eligible),
            'last_event': max((stat._aware(t).isoformat() for t, _ in eligible), default=None),
            'max_event_id': max((n for _, n in eligible), default=None)}


def _validate_candidate(histories: dict[int, list[Any]], kind: str, boundary: datetime,
                        parameters: list[float], now: datetime) -> dict:
    """Replay all prior events; only score forecasts at/after temporal holdout boundary."""
    candidate, default, legacy, outcomes = [], [], [], []
    heldout_ids = set()
    bins = set()
    for key, history in histories.items():
        baseline, _, _ = stat._replay(history, kind, now=now)
        optimized, _, _ = stat._replay(history, kind, now=now, parameters=parameters)
        if len(baseline) != len(optimized):
            raise ValueError('FSRS candidate replay changed event eligibility')
        for original, proposed in zip(baseline, optimized):
            if original['at'] < boundary:
                continue
            if original['at'] != proposed['at'] or original['outcome'] != proposed['outcome']:
                raise ValueError('FSRS candidate and baseline observations misaligned')
            heldout_ids.add(key)
            bins.add(0 if original['gap_days'] < 4 else 1 if original['gap_days'] < 15 else 2)
            default.append(original['predicted'])
            candidate.append(proposed['predicted'])
            legacy.append(original['legacy_probability'])
            outcomes.append(original['outcome'])
    brier = lambda probabilities: (sum((p-y)**2 for p,y in zip(probabilities,outcomes)) / len(outcomes)
                                   if outcomes else None)
    return {'holdout_samples': len(outcomes), 'holdout_distinct_items': len(heldout_ids),
            'holdout_failures': outcomes.count(0), 'holdout_interval_bins': len(bins),
            'brier_optimized': brier(candidate), 'brier_default': brier(default),
            'brier_v14': brier(legacy),
            'calibration_error': (abs(sum(candidate)/len(candidate) - sum(outcomes)/len(outcomes))
                                  if outcomes else None),
            'expected_recall_percent': round(100*sum(candidate)/len(candidate), 1) if outcomes else None,
            'observed_recall_percent': round(100*sum(outcomes)/len(outcomes), 1) if outcomes else None}


def _passes_validation(metrics: dict) -> bool:
    return bool(metrics['holdout_samples'] >= MIN_HOLDOUT_SPACED
                and metrics['holdout_distinct_items'] >= MIN_DISTINCT_HOLDOUT_ITEMS
                and metrics['holdout_failures'] >= MIN_HOLDOUT_FAILURES
                and metrics['holdout_interval_bins'] >= MIN_INTERVAL_BINS
                and metrics['brier_optimized'] is not None
                and metrics['brier_optimized'] + MIN_IMPROVEMENT_OVER_DEFAULT <= metrics['brier_default']
                and metrics['brier_optimized'] <= metrics['brier_v14'] + MAX_HOLDOUT_BRIER_REGRESSION_V14
                and metrics['calibration_error'] <= MAX_CALIBRATION_ERROR)


def evaluate_scope(histories: dict[int, list[Any]], kind: str, *, now: datetime | None = None,
                   optimizer_factory: Callable | None = None) -> tuple[dict, list[float] | None]:
    """Train only on pre-holdout review logs. No DB mutations here.

    optimizer_factory injection is for deterministic tests; real worker uses
    official fsrs.Optimizer.compute_optimal_parameters() with 21 weights.
    """
    now = now or utcnow()
    base = {'method': 'FSRS-6 oficial: otimização completa dos 21 parâmetros; holdout temporal',
            'retention_target_percent': 90, 'data_fingerprint': _fingerprint(histories, now),
            'limitations': ('Cards são autoavaliações e questões repetidas podem ter familiaridade. '
                            'Previsões de retenção não são previsão de acertos na prova.')}
    events = _events_for_scope(histories, kind, now)
    base['spaced_samples'] = len(events)
    if len(events) < MIN_OPTIMIZER_SPACED_TRAIN + MIN_HOLDOUT_SPACED:
        return {**base, 'status': 'aguardando', 'reason': 'Histórico espaçado insuficiente'}, None
    # Choose one calendar-time boundary; events from the cutoff time stay in holdout.
    boundary = events[int(len(events) * .8)][0]
    train = [(t,key,o) for t,key,o in events if t < boundary]
    holdout = [(t,key,o) for t,key,o in events if t >= boundary]
    base.update(training_spaced=len(train), validation_spaced=len(holdout),
                training_items=len({key for _,key,_ in train}),
                training_failures=sum(o['outcome']==0 for _,_,o in train),
                training_interval_bins=stat._bins([o for _,_,o in train]),
                validation_start=boundary.isoformat())
    if (len(train) < MIN_OPTIMIZER_SPACED_TRAIN or len(holdout) < MIN_HOLDOUT_SPACED
            or base['training_items'] < MIN_DISTINCT_TRAIN_ITEMS
            or base['training_failures'] < MIN_TRAIN_FAILURES
            or base['training_interval_bins'] < MIN_INTERVAL_BINS):
        return {**base, 'status': 'aguardando', 'reason': 'Diversidade ou quantidade de treino insuficiente'}, None

    # A ReviewLog includes the full within-item pre-cutoff sequence, including
    # initial review and same-day events. Crucially: no holdout review enters optimization.
    from fsrs import ReviewLog, Rating, Scheduler
    training_logs = []
    for key, history in histories.items():
        for entry in sorted(history, key=lambda r:(stat._aware(r.created_at), r.id)):
            at = stat._aware(entry.created_at)
            if at >= boundary or at > stat._aware(now):
                continue
            rating = stat._rating(entry, kind, Rating)
            if rating is not None:
                training_logs.append(ReviewLog(card_id=key, rating=rating,
                                               review_datetime=at, review_duration=None))
    if optimizer_factory is None:
        from fsrs import Optimizer
        optimizer_factory = Optimizer
    weights = [float(x) for x in optimizer_factory(training_logs).compute_optimal_parameters()]
    # Validate API shape and numeric bounds with the actual FSRS Scheduler.
    Scheduler(parameters=weights, desired_retention=stat.TARGET_RETENTION,
              learning_steps=(), relearning_steps=(), maximum_interval=60, enable_fuzzing=False)
    from fsrs.scheduler import DEFAULT_PARAMETERS
    if len(weights) != 21 or all(abs(a-b) < 1e-9 for a,b in zip(weights,DEFAULT_PARAMETERS)):
        return {**base, 'status': 'sem_melhoria', 'reason': 'Otimizador devolveu os parâmetros padrão'}, None
    metrics = _validate_candidate(histories, kind, boundary, weights, now)
    passed = _passes_validation(metrics)
    return {**base, **metrics, 'status': 'aprovado' if passed else 'rejeitado',
            'reason': ('Superou os critérios de validação temporal' if passed else
                       'Modelo não demonstrou ganho seguro no conjunto reservado')}, weights if passed else None



def _should_roll_back(histories: dict[int, list[Any]], kind: str, now: datetime,
                      record: RetentionProfile) -> tuple[bool, dict | None]:
    """Drift test on genuinely new observations, not the fitted dataset."""
    if not record.optimizer_active or not record.optimizer_parameters:
        return False, None
    stamp = (record.optimizer_metrics or {}).get('last_approved_at')
    if not stamp:
        return False, None
    boundary = datetime.fromisoformat(stamp)
    metrics = _validate_candidate(histories, kind, boundary, record.optimizer_parameters, now)
    if metrics['holdout_samples'] < 50 or metrics['holdout_failures'] < 5:
        return False, metrics
    regression = (metrics['brier_optimized'] > min(metrics['brier_v14'], metrics['brier_default']) + 0.03
                  or metrics['calibration_error'] > 0.20)
    return regression, metrics

def optimize_profiles(db: Session, *, now: datetime | None = None,
                      scope_filter: str | None = None, dry_run: bool = True,
                      optimizer_factory: Callable | None = None) -> list[dict]:
    """Called by isolated CLI, not by the Render web-service refresh handler.

    Idempotent across weekly calls without new events. A rejected update never
    replaces an already-approved model. No secrets are logged.
    """
    now = now or utcnow()
    all_histories = stat.collect_histories(db)
    if scope_filter:
        all_histories = {s:h for s,h in all_histories.items() if s == scope_filter}
    outcomes = []
    for scope, histories in sorted(all_histories.items()):
        record = db.get(RetentionProfile, scope)
        fingerprint = _fingerprint(histories, now)
        old = record.optimizer_metrics if record else None
        if old and old.get('data_fingerprint') == fingerprint:
            outcomes.append({'scope':scope, 'status':'sem_alteracoes', 'active': bool(record.optimizer_active)})
            continue
        kind = scope.split(':', 1)[0]
        summary, weights = evaluate_scope(histories, kind, now=now, optimizer_factory=optimizer_factory)
        status = summary['status']
        outcome = {'scope':scope, 'status':status,
                   'active': bool(weights is not None or (record and record.optimizer_active)),
                   'spaced_samples':summary['spaced_samples']}
        outcomes.append(outcome)
        if dry_run:
            continue
        if record is None:
            record = RetentionProfile(scope=scope, stage='observando', active=False,
                                      factor=1.0, updated_at=now)
            db.add(record)
        last_approved = (old or {}).get('last_approved_at')
        if weights is not None:
            summary['last_approved_at'] = now.isoformat()
            record.optimizer_parameters = weights
            record.optimizer_active = True
        else:
            if last_approved:
                summary['last_approved_at'] = last_approved
            # A failed candidate does not instantly disable a validated model.
            # Only new outcomes since activation can demonstrate drift.
            if record.optimizer_active:
                rollback, live_metrics = _should_roll_back(histories, kind, now, record)
                summary['post_activation_validation'] = live_metrics
                if rollback:
                    status = 'revertido'
                    summary['status'] = status
                    summary['reason'] = 'Previsões pioraram em novas revisões; retorno ao fallback'
                    record.optimizer_active = False
                else:
                    status = 'mantido'
                    summary['status'] = status
                    summary['reason'] = 'Modelo validado anterior mantido; candidato não aprovado'
        record.optimizer_status = status
        record.optimizer_metrics = summary
        record.optimizer_updated_at = now
        outcome['status'] = status
        outcome['active'] = bool(record.optimizer_active)
        db.add(RetentionModelRun(scope=scope, session_id=None, created_at=now,
             stage='otimizador_' + status, active=bool(record.optimizer_active),
             factor=record.factor, metrics=summary))
        db.commit()
    return outcomes
