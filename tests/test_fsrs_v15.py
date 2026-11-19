"""Validation, rollout and persistence tests for v0.15.

The real FSRS integration requires the official fsrs package at deployment;
these unit tests simulate its interface because CI may run without optional deps.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import statistical_retention as stat


def _entry(n, days=0, **values):
    return SimpleNamespace(id=n, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=days), **values)


def test_conservative_question_rating_mapping():
    class Ratings:
        Again = 1
        Hard = 2
        Good = 3
        Easy = 4

    assert stat._rating(_entry(1,is_correct=False,confidence=3), 'question', Ratings) == 1
    assert stat._rating(_entry(2,is_correct=True,confidence=1), 'question', Ratings) == 1
    assert stat._rating(_entry(3,is_correct=True,confidence=2), 'question', Ratings) == 1
    assert stat._rating(_entry(4,is_correct=True,confidence=3), 'question', Ratings) == 3
    assert stat._rating(_entry(5,is_correct=True,confidence=None), 'question', Ratings) is None


def test_conservative_topic_rating_mapping():
    class Ratings:
        Again = 1
        Hard = 2
        Good = 3
        Easy = 4

    attrs = dict(critical_gap=False, assistance_level=0, accuracy_level=3, recall_level=3)
    assert stat._rating(_entry(1,grade=4, **attrs), 'topic', Ratings) == 4
    assert stat._rating(_entry(2,grade=3, **attrs), 'topic', Ratings) == 3
    assert stat._rating(_entry(3,grade=2, **attrs), 'topic', Ratings) == 1
    assert stat._rating(_entry(4,grade=4, critical_gap=True, assistance_level=0,
                               accuracy_level=3, recall_level=3), 'topic', Ratings) == 1
    assert stat._rating(_entry(5,grade=4, critical_gap=False, assistance_level=3,
                               accuracy_level=3, recall_level=3), 'topic', Ratings) == 1
    assert stat._rating(_entry(6,grade=4, critical_gap=False, assistance_level=0,
                               accuracy_level=3, recall_level=None), 'topic', Ratings) is None


def make_synthetic(monkeypatch, *, legacy_prob=0.6):
    # 18 distinct items × 17 spaced events = 306 observations.
    # There are successes, failures, and intervals in all three ranges.
    def replay(records, kind, now=None):
        result=[]
        for i in range(17):
            gap = (2, 7, 21)[i % 3]
            result.append({
                'at': datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i * 4 + records[0]),
                'gap_days': gap, 'stability_days': 10.0,
                'predicted': 0.9, 'legacy_probability': legacy_prob,
                'outcome': int((i + records[0]) % 11 != 0),
            })
        return result, None, None

    monkeypatch.setattr(stat, '_fsrs', lambda: ('fake',))
    monkeypatch.setattr(stat, '_replay', replay)
    return [[i] for i in range(18)]


def test_statistical_model_activates_when_heldout_is_reliable(monkeypatch):
    histories=make_synthetic(monkeypatch, legacy_prob=0.52)
    result=stat._profile_summary(histories, 'topic', datetime(2026, 12, 1, tzinfo=timezone.utc))
    assert result['samples'] == 18 * 17
    assert result['training_samples'] >= stat.MIN_TRAIN
    assert result['validation_samples'] >= stat.MIN_VALIDATION
    assert result['interval_bins'] == 3
    assert result['active'] is True
    assert result['stage'] == 'ativo'
    assert result['holdout_brier_candidate'] < result['holdout_brier_v14']
    assert 0 < result['holdout_observed_recall_percent'] < 100


def test_statistical_model_stays_shadow_when_legacy_predicts_better(monkeypatch):
    histories=make_synthetic(monkeypatch, legacy_prob=0.87)
    result=stat._profile_summary(histories, 'topic', datetime(2026, 12, 1, tzinfo=timezone.utc))
    assert result['active'] is False
    assert result['stage'] == 'validando'
    assert result['factor'] == 1.0


def test_insufficient_data_never_activates(monkeypatch):
    histories=make_synthetic(monkeypatch)
    result=stat._profile_summary(histories[:3], 'question', datetime(2026, 12, 1, tzinfo=timezone.utc))
    assert result['active'] is False
    assert result['distinct_items'] == 3


def test_interval_blending_and_old_fallback():
    assert stat.blend_interval(10, 50, False) == 10
    assert stat.blend_interval(10, 50, True) == 12  # max 25% conservative change
    assert stat.blend_interval(20, 2, True) == 15
    assert stat.blend_interval(30, 60, True, maximum=30) == 30


def test_retention_profile_created_on_session_refresh(client, monkeypatch):
    # Real FSRS is not installed in this test environment; graceful fallback.
    monkeypatch.setattr(stat, '_fsrs', lambda: None)
    subject = client.post('/api/subjects', json={'name':'Bancários'}).json()['id']
    topic = client.post('/api/topics', json={'subject_id':subject, 'title':'Mercado Aberto'}).json()['id']
    s = client.post('/api/sessions').json()['id']
    reply = client.post(f'/api/sessions/{s}/topic-reviews', json={'topic_id':topic, 'grade':3})
    assert reply.status_code == 201, reply.text
    close = client.post(f'/api/sessions/{s}/refresh')
    assert close.status_code == 200, close.text
    profiles = client.get('/api/retention-models').json()
    profile = next(x for x in profiles if x['scope'] == f'topic:{subject}')
    assert profile['stage'] == 'indisponivel'
    assert profile['active'] is False
    queue = client.get(f'/api/queue?subject_id={subject}').json()
    assert queue['topics'][0]['retention_model']['source'] == 'regras v0.14'
    assert queue['topics'][0]['interval_days'] >= 1


def test_statistical_model_never_changes_question_subject_scope(client):
    a=client.post('/api/subjects',json={'name':'Matemática'}).json()['id']
    b=client.post('/api/subjects',json={'name':'Português'}).json()['id']
    client.post('/api/topics',json={'subject_id':a,'title':'Frações'})
    client.post('/api/topics',json={'subject_id':b,'title':'Concordância'})
    q=client.get(f'/api/queue?subject_id={a}').json()
    assert all(row['retention_model']['scope'] == f'topic:{a}' for row in q['topics'])
    q2=client.get(f'/api/queue?subject_id={b}').json()
    assert all(row['retention_model']['scope'] == f'topic:{b}' for row in q2['topics'])
