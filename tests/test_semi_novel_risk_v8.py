"""v0.8: risco limitado, evidência enviesada e métricas sem vazamento entre matérias."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import get_db
from app.engine import (adjusted_risk, build_queue, empirical_risk_adjustment, ranking_score,
                        semi_novel_progress, question_interval, question_forgetting_risk)
from app.models import Question, QuestionAttempt, TopicReview

NOW = datetime(2026, 11, 18, 18, 0, tzinfo=timezone.utc)


def test_risk_bonus_is_bounded_and_base_formula_is_unchanged(client):
    subject = client.post('/api/subjects', json={'name': 'Português'}).json()['id']
    topic = client.post('/api/topics', json={'subject_id': subject, 'title': 'Crase', 'importance': 4}).json()['id']
    sid = client.post('/api/sessions').json()['id']
    client.post(f'/api/sessions/{sid}/topic-reviews', json={'topic_id': topic, 'grade': 2, 'difficulty': 3})
    result = client.get(f'/api/queue?subject_id={subject}').json()['topics'][0]
    components = result['priority_components']
    expected = round(.35*components['D']+.30*components['T']+.25*components['E']+.10*components['I'], 2)
    assert result['priority'] == expected
    assert 0 <= result['risk_priority_bonus'] <= 8
    assert result['ranking_score'] == min(100, round(expected + result['risk_priority_bonus'], 2))
    assert ranking_score(100, 100) == (100, 8)
    assert ranking_score(10, None) == (10, 0)


def test_tag_does_not_change_priority_but_changes_mastery_evidence(client):
    sub = client.post('/api/subjects', json={'name': 'Matemática'}).json()['id']
    topic = client.post('/api/topics', json={'subject_id': sub, 'title': 'Juros'}).json()['id']
    question = client.post('/api/questions', json={'subject_id': sub, 'url': 'https://example.org/juros'}).json()
    before = client.get(f'/api/queue?subject_id={sub}').json()['topics'][0]
    modified = client.patch(f"/api/questions/{question['id']}", json={
        'subject_id': sub, 'topic_id': topic, 'url': 'https://example.org/juros',
    })
    assert modified.status_code == 200
    after = client.get(f'/api/queue?subject_id={sub}').json()['topics'][0]
    assert before['priority'] == after['priority']
    assert before['ranking_score'] == after['ranking_score']
    assert after['mastery_evidence']['distinct_questions'] == 0
    sid = client.post('/api/sessions').json()['id']
    client.post(f'/api/sessions/{sid}/question-attempts', json={
        'question_id': question['id'], 'is_correct': False, 'confidence': 1, 'error_type': 'concept',
    })
    later = client.get(f'/api/queue?subject_id={sub}').json()['topics'][0]
    assert later['mastery_evidence']['distinct_questions'] == 1
    assert later['mastery_evidence']['pending_concept_errors'] == 1
    assert later['priority'] == before['priority']


def test_semi_novel_requires_spaced_attempts_on_distinct_links():
    questions = [Question(id=1), Question(id=2), Question(id=3)]
    def event(q, days, correct, confidence=3):
        return QuestionAttempt(question_id=q, is_correct=correct, confidence=confidence,
                               created_at=NOW-timedelta(days=days))
    history = {
        1: [event(1, 29, False), event(1, 20, True), event(1, 9, True)],
        2: [event(2, 20, False), event(2, 10, True, confidence=2)],
        3: [event(3, 2, True)],
    }
    progress = semi_novel_progress(questions, history, NOW)
    assert progress['registered'] == 3
    assert progress['reviewed_in_app'] == 3
    assert progress['spaced_distinct'] == 2
    assert progress['spaced_secure'] == 1
    assert progress['spaced_secure_percent'] == 50
    assert progress['sufficient_sample'] is False
    assert progress['trend_pp'] is None
    assert progress['target_percent'] == 90
    assert 'não estima nota' in progress['interpretation']


def test_semi_novel_separates_subjects_and_displays_no_invented_zero(client):
    a = client.post('/api/subjects', json={'name': 'Português'}).json()['id']
    b = client.post('/api/subjects', json={'name': 'Matemática'}).json()['id']
    qa = client.post('/api/questions', json={'subject_id': a, 'url': 'https://example.com/a'}).json()['id']
    qb = client.post('/api/questions', json={'subject_id': b, 'url': 'https://example.com/b'}).json()['id']
    sid = client.post('/api/sessions').json()['id']
    client.post(f'/api/sessions/{sid}/question-attempts', json={
        'question_id': qa, 'is_correct': False, 'confidence': 1})
    client.post(f'/api/sessions/{sid}/refresh')
    second_session = client.post('/api/sessions').json()['id']
    with next(client.app.dependency_overrides[get_db]()) as db:
        for q in db.scalars(select(QuestionAttempt)).all():
            q.created_at = NOW - timedelta(days=10)
        db.add(QuestionAttempt(question_id=qa, session_id=second_session, is_correct=True, confidence=3,
                               created_at=NOW))
        db.commit()
        a_progress = build_queue(db, NOW, subject_id=a)['semi_novel_progress']
        b_progress = build_queue(db, NOW, subject_id=b)['semi_novel_progress']
    assert (a_progress['registered'], a_progress['spaced_distinct'], a_progress['spaced_secure_percent']) == (1, 1, 100)
    assert (b_progress['registered'], b_progress['spaced_distinct'], b_progress['spaced_secure_percent']) == (1, 0, None)


def test_empirical_adjustment_requires_sufficient_subject_history():
    def attempt(days, correct):
        return QuestionAttempt(is_correct=correct, confidence=3,
                               created_at=NOW-timedelta(days=days))
    small = [[attempt(10, True), attempt(2, False)] for _ in range(5)]
    bias, samples = empirical_risk_adjustment(small, question_interval, question_forgetting_risk,
                                               lambda r: not r.is_correct, NOW)
    assert samples == 5 and bias == 0
    big = small + [[attempt(14, True), attempt(2, False)] for _ in range(35)]
    bias, samples = empirical_risk_adjustment(big, question_interval, question_forgetting_risk,
                                               lambda r: not r.is_correct, NOW)
    assert samples == 40
    assert 0 < bias <= 0.12
    assert adjusted_risk(95, bias) <= 100


def test_ui_and_api_label_biased_data_and_avoid_fake_exam_projection(client):
    html = client.get('/').text
    js = client.get('/static/app.js').text
    assert 'id="semiNovelProgress"' in html
    assert 'questões variadas (não precisam ser inéditas)' in html
    assert 'Não prevê nota na prova' in js
    assert 'ranking_score' in js
    assert '/static/app.js?v=9' in html
    sub = client.post('/api/subjects', json={'name': 'Conhecimentos Bancários'}).json()['id']
    summary = client.get(f'/api/queue?subject_id={sub}').json()['semi_novel_progress']
    assert summary['spaced_secure_percent'] is None
