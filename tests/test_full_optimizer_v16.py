"""Full-optimizer gates, temporal holdout, persistence and fallback without torch.

Mocked FSRS predictions are a deterministic contract test, NOT a claim of
scientifically calibrated model performance. Official dependency is exercised
by the optional integration test in test_fsrs_real_dependency_v15.py.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import sys
import types

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import RetentionProfile, RetentionModelRun
from app import statistical_retention as stat
from app import full_fsrs_optimizer as full

BASE = datetime(2025, 1, 1, tzinfo=timezone.utc)


def histories(count=40, reviews=34):
    result = {}
    for key in range(1, count+1):
        now = BASE + timedelta(days=key % 5)
        sequence=[]
        for j in range(reviews):
            now += timedelta(days=(2, 7, 21)[j % 3])
            good = key % 10 != 0 or j % 4 == 0
            sequence.append(SimpleNamespace(id=key*1000+j, question_id=key,
                           created_at=now, is_correct=good,
                           confidence=3 if good else 1))
        result[key]=sequence
    return result


def install_fake_fsrs(monkeypatch):
    fake = types.ModuleType('fsrs')
    scheduler = types.ModuleType('fsrs.scheduler')
    default_weights = [1.0] * 21
    scheduler.DEFAULT_PARAMETERS = tuple(default_weights)
    fake.ReviewLog = lambda **kwargs: SimpleNamespace(**kwargs)
    fake.Rating = SimpleNamespace(Again=1, Hard=2, Good=3, Easy=4)
    class FakeScheduler:
        def __init__(self, parameters, **kwargs):
            assert len(parameters) == 21
    fake.Scheduler = FakeScheduler
    monkeypatch.setitem(sys.modules, 'fsrs', fake)
    monkeypatch.setitem(sys.modules, 'fsrs.scheduler', scheduler)
    def fake_replay(sequence, kind, *, now=None, parameters=None):
        observations=[]
        for prior, row in zip(sequence, sequence[1:]):
            if now and row.created_at > now:
                continue
            gap=(row.created_at-prior.created_at).days
            if gap < 1:
                continue
            high = row.question_id % 10 != 0
            likelihood = (0.94 if high else 0.30) if parameters else 0.70
            observations.append(dict(at=row.created_at, gap_days=gap, outcome=int(row.is_correct),
                                    predicted=likelihood, legacy_probability=0.70,
                                    stability_days=7))
        return observations, None, None
    monkeypatch.setattr(stat, '_replay', fake_replay)
    return fake


def test_full_optimizer_waits_and_does_not_import_heavy_optimizer(monkeypatch):
    install_fake_fsrs(monkeypatch)
    summary, weights = full.evaluate_scope(histories(count=10,reviews=7), 'question',
        now=datetime(2027, 1, 1,tzinfo=timezone.utc))
    assert summary['status'] == 'aguardando'
    assert weights is None


def test_train_only_earlier_events_and_promote_after_holdout(monkeypatch):
    install_fake_fsrs(monkeypatch)
    received={}
    class FakeOptimizer:
        def __init__(self, logs):
            received['logs']=logs
        def compute_optimal_parameters(self):
            return [1.04] + [1.0]*20
    summary, weights=full.evaluate_scope(histories(), 'question',
        now=datetime(2027, 1, 1,tzinfo=timezone.utc), optimizer_factory=FakeOptimizer)
    assert summary['training_spaced'] >= 512
    assert summary['validation_spaced'] >= 100
    assert len(received['logs']) > 512
    assert all(x.review_datetime < datetime.fromisoformat(summary['validation_start']) for x in received['logs'])
    assert len(set(x.card_id for x in received['logs'])) >= 25
    assert summary['brier_optimized'] < summary['brier_default']
    assert summary['status'] == 'aprovado'
    assert len(weights) == 21


def test_candidate_rejected_if_no_improvement_over_default(monkeypatch):
    install_fake_fsrs(monkeypatch)
    def flat_replay(sequence, kind, *, now=None, parameters=None):
        obs=[]
        for prior,row in zip(sequence,sequence[1:]):
            if now and row.created_at > now: continue
            obs.append(dict(at=row.created_at, gap_days=(row.created_at-prior.created_at).days,
                            outcome=int(row.is_correct), predicted=0.7,legacy_probability=0.7,
                            stability_days=7))
        return obs,None,None
    monkeypatch.setattr(stat, '_replay',flat_replay)
    class FakeOptimizer:
        def __init__(self, logs): pass
        def compute_optimal_parameters(self): return [1.04]+[1.0]*20
    summary, weights=full.evaluate_scope(histories(), 'question',
        now=datetime(2027, 1, 1,tzinfo=timezone.utc),optimizer_factory=FakeOptimizer)
    assert summary['status'] == 'rejeitado'
    assert weights is None


def test_approved_parameters_saved_and_second_run_idempotent(monkeypatch):
    install_fake_fsrs(monkeypatch)
    class FakeOptimizer:
        def __init__(self, logs): pass
        def compute_optimal_parameters(self): return [1.04]+[1.0]*20
    monkeypatch.setattr(stat,'collect_histories',lambda db: {'question:8':histories()})
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            output=full.optimize_profiles(db,now=datetime(2027,1,1,tzinfo=timezone.utc),
                       dry_run=False,optimizer_factory=FakeOptimizer)
            assert output[0]['status']=='aprovado'
            record=db.get(RetentionProfile,'question:8')
            assert record.optimizer_active is True
            assert record.optimizer_parameters[0] == 1.04
            assert record.active is False  # v0.15 lightweight remains independent
            assert len(db.scalars(select(RetentionModelRun)).all()) == 1
            again=full.optimize_profiles(db,now=datetime(2027,1,8,tzinfo=timezone.utc),
                       dry_run=False,optimizer_factory=FakeOptimizer)
            assert again[0]['status']=='sem_alteracoes'
            assert len(db.scalars(select(RetentionModelRun)).all()) == 1
            profile=stat.public_profile(record)
            assert profile['optimizer']['active'] is True
            assert profile['optimizer']['parameters_count'] == 21
    finally:
        engine.dispose()


def test_dry_run_never_updates_database(monkeypatch):
    install_fake_fsrs(monkeypatch)
    monkeypatch.setattr(stat,'collect_histories',lambda db: {'question:1':histories(count=3, reviews=7)})
    engine = create_engine('sqlite+pysqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            full.optimize_profiles(db,dry_run=True)
            assert db.get(RetentionProfile,'question:1') is None
    finally: engine.dispose()


@pytest.mark.parametrize('status', ['aguardando', 'sem_melhoria', 'aprovado',
                                  'rejeitado', 'revertido', 'mantido'])
def test_optimizer_history_stage_fits_column(monkeypatch, status):
    monkeypatch.setattr(stat, 'collect_histories', lambda db: {'question:1': histories(count=1, reviews=2)})
    monkeypatch.setattr(full, 'evaluate_scope', lambda *args, **kwargs: (
        {'status': status, 'spaced_samples': 1}, None))
    engine = create_engine('sqlite+pysqlite://', poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            full.optimize_profiles(db, dry_run=False)
            run = db.scalar(select(RetentionModelRun))
            assert run.stage == 'otimizador_' + status
            assert len(run.stage) <= RetentionModelRun.__table__.c.stage.type.length
    finally:
        engine.dispose()


def test_schedulers_accept_custom_parameters_from_profile(monkeypatch):
    # No real fsrs is needed to prove queue forwards the 21 trained parameters.
    from app import engine as queue_engine
    captured=[]
    def estimate(history, kind, now, *, factor=1.0, parameters=None):
        captured.append((kind, factor, parameters))
        return {'expected_recall_percent':85, 'fsrs_interval_days':8,'stability_days':14}
    monkeypatch.setattr(queue_engine,'item_estimate',estimate)
    engine = create_engine('sqlite+pysqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    from app.models import Subject, Topic, Question
    try:
        with Session(engine) as db:
            db.add(Subject(id=5,name='Bancários'))
            db.add(Topic(id=10,subject_id=5,title='Compulsório'))
            db.add(Question(id=12,subject_id=5,statement='Teste de compulsório',url='https://example.org/q'))
            db.add(RetentionProfile(scope='topic:5',optimizer_active=True,
                 optimizer_status='aprovado', optimizer_parameters=[1.04]+[1.0]*20))
            db.add(RetentionProfile(scope='question:5',optimizer_active=True,
                 optimizer_status='aprovado', optimizer_parameters=[1.04]+[1.0]*20))
            db.commit()
            response=queue_engine.build_queue(db,subject_id=5)
            assert response['topics'][0]['retention_model']['source'].startswith('FSRS-6 otimizado')
            assert response['questions'][0]['retention_model']['source'].startswith('FSRS-6 otimizado')
            assert len(captured)>=2 and all(p is not None and len(p)==21 and factor==1.0
                                            for _,factor,p in captured)
    finally: engine.dispose()


def test_rollback_requires_new_outcomes_after_approval(monkeypatch):
    install_fake_fsrs(monkeypatch)
    # The approved weights are not judged against the original training set.
    model=RetentionProfile(scope='question:1', optimizer_active=True,
                           optimizer_parameters=[1.04]+[1.0]*20,
                           optimizer_metrics={'last_approved_at':'2027-01-01T00:00:00+00:00'})
    rolled, metrics=full._should_roll_back(histories(), 'question',
                datetime(2027,1,2,tzinfo=timezone.utc), model)
    assert rolled is False
    assert metrics['holdout_samples'] == 0
    # Test future observations with a deliberately miscalibrated old model.
    def bad_validation(histories, kind, boundary, parameters, now):
        assert boundary == datetime(2027,1,1,tzinfo=timezone.utc)
        return {'holdout_samples': 100, 'holdout_failures': 15,
                'brier_optimized':0.32, 'brier_default':0.12,
                'brier_v14':0.10, 'calibration_error':0.25}
    monkeypatch.setattr(full, '_validate_candidate', bad_validation)
    rolled, _ = full._should_roll_back(histories(), 'question',
                datetime(2027,12,1,tzinfo=timezone.utc), model)
    assert rolled is True


def test_rejected_training_does_not_erase_previous_approved_parameters(monkeypatch):
    install_fake_fsrs(monkeypatch)
    monkeypatch.setattr(stat,'collect_histories',lambda db: {'question:8':histories()})
    from app import full_fsrs_optimizer as mod
    def reject(histories, kind, *, now, optimizer_factory):
        return {'status':'rejeitado', 'spaced_samples':800,
                'reason':'sem ganho', 'data_fingerprint':mod._fingerprint(histories,now)}, None
    monkeypatch.setattr(mod,'evaluate_scope',reject)
    engine=create_engine('sqlite+pysqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            original=[1.04]+[1.0]*20
            db.add(RetentionProfile(scope='question:8',optimizer_active=True,
                 optimizer_status='aprovado', optimizer_parameters=original,
                 optimizer_metrics={'last_approved_at':'2027-12-01T00:00:00+00:00'}))
            db.commit()
            out=mod.optimize_profiles(db,now=datetime(2027,1,1,tzinfo=timezone.utc),
                                      dry_run=False)
            profile=db.get(RetentionProfile,'question:8')
            assert profile.optimizer_active is True
            assert profile.optimizer_parameters == original
            assert profile.optimizer_status == 'mantido'
    finally: engine.dispose()
