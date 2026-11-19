"""v0.14: evidência temporal, aplicação opcional e duas etapas sem dados falsos."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.assessment import inferred_grade, qualifies_as_spaced_success
from app.db import get_db
from app.engine import (build_queue, observed_retention_interval,
                        retention_interval_validation, retention_observations,
                        topic_interval, question_interval)
from app.models import QuestionAttempt, TopicReview


def make_reviews(grades, spacing, *, structured=True, start=None):
    start = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [TopicReview(grade=grade, difficulty=1,
                        critical_gap=False, created_at=start + timedelta(days=i * spacing),
                        recall_level=3 if structured else None,
                        accuracy_level=3 if structured else None,
                        assistance_level=0 if structured else None,
                        gap_level=0 if structured else None)
            for i, grade in enumerate(grades)]


def test_grade_does_not_reward_references_or_unverified_application():
    assert inferred_grade(3, 3, 0, 0, None) == 4  # não testou: não penalizar
    assert inferred_grade(3, 3, 0, 0, 2) == 4
    assert inferred_grade(3, 3, 0, 0, 1) == 3
    assert inferred_grade(3, 3, 0, 0, 0) == 2
    assert inferred_grade(3, 3, 2, 0, 2) == 2  # dica limita nota
    assert inferred_grade(3, 3, 3, 0, 2) == 1  # consulta limita nota
    assert inferred_grade(3, 1, 0, 0, 2) == 1  # erro conceitual grave
    assert inferred_grade(3, 3, 0, 3, 2) == 1
    assert inferred_grade(0, 3, 0, 0, 2) == 0


def test_structured_applications_persist_and_legacy_fields_remain_compatible(client):
    sid = client.post('/api/subjects', json={'name':'Matemática'}).json()['id']
    topics = [client.post('/api/topics', json={'subject_id': sid, 'title':t}).json()['id']
              for t in ('Frações', 'Porcentagem', 'Probabilidade', 'Álgebra')]
    session = client.post('/api/sessions').json()['id']
    base = {'recall_level':3, 'accuracy_level':3, 'assistance_level':0, 'gap_level':0}
    for topic, choice, expected in zip(topics[:3], (None, 0, 2), (4, 2, 4)):
        result = client.post(f'/api/sessions/{session}/topic-reviews', json={
            'topic_id':topic, **base, 'application_level':choice})
        assert result.status_code == 201, result.text
        assert result.json()['inferred_grade'] == expected
    with next(client.app.dependency_overrides[get_db]()) as db:
        a,b,c = [db.query(TopicReview).filter(TopicReview.topic_id == t).one() for t in topics[:3]]
        assert a.application_level is None and a.applied_to_new_questions is False
        assert b.application_level == 0 and b.applied_to_new_questions is False
        assert c.application_level == 2 and c.applied_to_new_questions is True
    legacy = client.post(f'/api/sessions/{session}/topic-reviews', json={
        'topic_id': topics[3], 'grade':4, 'applied_to_new_questions':True})
    assert legacy.status_code == 201
    assert client.post(f'/api/sessions/{session}/topic-reviews', json={
        'topic_id':topics[0], **base, 'application_level':2}).status_code == 409
    assert client.post(f'/api/sessions/{session}/topic-reviews', json={
        'topic_id': topics[0], **base, 'application_level': 2,
        'applied_to_new_questions': True, 'grade':4}).status_code == 422
    assert client.post(f'/api/sessions/{session}/topic-reviews', json={
        'topic_id': topics[0], **base, 'application_level': 0,
        'applied_to_new_questions': True}).status_code == 422


def test_application_failed_blocks_spaced_success_even_if_grade_is_legacy_four():
    row = TopicReview(grade=4, recall_level=3, accuracy_level=3,
                      assistance_level=0, gap_level=0, application_level=0,
                      critical_gap=False)
    assert not qualifies_as_spaced_success(row)
    row.application_level = None
    assert qualifies_as_spaced_success(row)
    row.assistance_level = 3
    assert not qualifies_as_spaced_success(row)


def test_short_successes_cannot_validate_long_interval():
    events = make_reviews([4] * 20, spacing=3)
    check = retention_interval_validation(events, 30, topic_interval, qualifies_as_spaced_success)
    assert check['spaced_samples'] == 19
    assert check['comparable_samples'] == 0
    assert not check['evidence_sufficient_for_growth']
    assert observed_retention_interval(events, 30, qualifies_as_spaced_success) == 30
    assert check['by_actual_interval'][0]['samples'] == 19


def test_successful_spaced_reviews_validate_comparable_interval():
    events = make_reviews([4] * 15, spacing=31)
    check = retention_interval_validation(events, 30, topic_interval, qualifies_as_spaced_success)
    assert check['comparable_samples'] == 14
    assert check['comparable_successes'] == 14
    assert check['evidence_sufficient_for_growth']
    assert 30 < observed_retention_interval(events, 30, qualifies_as_spaced_success) <= 38
    assert check['by_actual_interval'][-1]['samples'] == 14


def test_legacy_successes_do_not_trigger_interval_growth():
    old = make_reviews([4] * 15, spacing=31, structured=False)
    assert observed_retention_interval(old, 30, qualifies_as_spaced_success) == 30
    check = retention_interval_validation(old, 30, topic_interval, qualifies_as_spaced_success)
    assert check['structured_spaced_samples'] == 0
    assert not check['evidence_sufficient_for_growth']


def test_pooling_cannot_inflate_individual_intervals_without_local_evidence():
    short = make_reviews([4,4,4], spacing=31)
    pooled = [make_reviews([4]*20, spacing=31, start=datetime(2024,1,1,tzinfo=timezone.utc))]
    assert observed_retention_interval(short, 30, qualifies_as_spaced_success, pooled) == 30


def test_repeated_early_failures_shorten_interval():
    events = make_reviews([4]+[1]*14, spacing=2)
    adjusted = observed_retention_interval(events, 30, qualifies_as_spaced_success)
    assert 23 <= adjusted < 30
    audit = retention_interval_validation(events, 30, topic_interval, qualifies_as_spaced_success)
    assert audit['spaced_samples'] == 14


def test_same_day_recalls_do_not_count_as_spaced_evidence():
    events = make_reviews([4] * 12, spacing=0.1)
    assert not retention_observations(events, topic_interval, qualifies_as_spaced_success)
    assert observed_retention_interval(events, 30, qualifies_as_spaced_success) == 30


def test_question_intervals_are_audited_independently_from_topic_reviews():
    base = datetime(2026,1,1,tzinfo=timezone.utc)
    attempts = [QuestionAttempt(is_correct=True, confidence=3,
                                created_at=base+timedelta(days=31*i)) for i in range(12)]
    audit = retention_interval_validation(attempts, 30, question_interval,
                                          lambda x: x.is_correct and x.confidence == 3)
    assert audit['spaced_samples'] == 11
    assert audit['comparable_successes'] == 11
    assert audit['evidence_sufficient_for_growth']
    assert observed_retention_interval(attempts, 30, lambda x: x.is_correct and x.confidence == 3) > 30


def test_ui_has_two_distinct_phases_and_optional_application(client):
    html=client.get('/').text
    js=client.get('/static/app.js').text
    assert 'id="reviewBefore"' in html
    assert 'id="reviewAfter"' in html
    assert 'id="confirmReviewRecall"' in html
    assert 'name="application_level" value="not_tested" checked' in html
    assert "$('reviewBefore').hidden=true;$('reviewAfter').hidden=false;" in js
    assert 'retention_validation' in js


def test_both_queues_expose_observed_retention_without_changing_session_protection(client):
    subject=client.post('/api/subjects',json={'name':'Bancários'}).json()['id']
    topic=client.post('/api/topics',json={'subject_id':subject,'title':'Crédito'}).json()['id']
    question=client.post('/api/questions',json={'subject_id':subject,'url':'https://example.org/questao14'}).json()['id']
    sid=client.post('/api/sessions').json()['id']
    queue=client.get(f'/api/sessions/{sid}/queue?subject_id={subject}').json()
    assert queue['topics'][0]['retention_validation']['spaced_samples']==0
    assert queue['questions'][0]['retention_validation']['spaced_samples']==0
    assert client.post(f'/api/sessions/{sid}/topic-reviews',json={
        'topic_id':topic, 'recall_level':3,'accuracy_level':3,'assistance_level':0,'gap_level':0}).status_code==201
    assert client.post(f'/api/sessions/{sid}/question-attempts',json={
        'question_id':question,'is_correct':True,'confidence':3}).status_code==201
    new=client.get(f'/api/sessions/{sid}/queue?subject_id={subject}').json()
    assert not new['topics'] and not new['questions']
